"""Optional integration test against the real pinned Carrot parser/live source.

CARROT_HELPER_ROOT=/path/to/carrot python3 -m unittest discover -s tests -p test_hkg_renderer.py -v
No GPU, USB, vehicle data or control processes are used.
"""
import importlib.util
import ast
import base64
import os
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hkg_hud', ROOT / 'hkg/hkg_hud.py')
hkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hkg)


@unittest.skipUnless(os.environ.get('CARROT_HELPER_ROOT'), 'requires the pinned Carrot helper checkout')
class RendererTests(unittest.TestCase):
  def test_actual_carrot_output_gate_allows_live_standby_without_faking_ignition(self):
    helper = Path(os.environ['CARROT_HELPER_ROOT']).resolve()
    def load_class(path, name, namespace):
      tree = ast.parse(path.read_text())
      node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
      exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
      return namespace[name]

    value = [None]
    base = load_class(helper / 'tools/jetlink/hud.py', 'DisplayParams',
                      {'time': time, 'base64': base64, 'read_snapshot': lambda: value[0]})
    settings = hkg.display_params(base, types.SimpleNamespace(get=lambda key: None))
    module = types.ModuleType('openpilot.common.params')
    module.Params = settings
    gate_type = load_class(helper / 'openpilot/selfdrive/carrot/cluster/main.py', 'ClusterHudOutputGateParamReader',
                           {'CLUSTER_HUD_DEBUG_PARAM': 'ClusterHudDebug'})
    with patch.dict(sys.modules, {'openpilot.common.params': module}):
      for onroad in (None, False, True, False):
        with self.subTest(onroad=onroad):
          value[0] = None if onroad is None else (0., {'params': {
            'IsOnroad': base64.b64encode(b'1' if onroad else b'0').decode()}})
          params = settings()
          # Same startup predicate as the pinned hud.main(), plus its real gate.
          self.assertTrue(params.get_int('ClusterHud') == 1 and
                          (params.get_bool('IsOnroad') or params.get_int('ClusterHudDebug') >= 1))
          gate = gate_type()
          self.assertTrue(gate.allowed())
          self.assertEqual(gate.read_mode(), 1)
          self.assertEqual(params.get_bool('IsOnroad'), bool(onroad))
          self.assertEqual(params.get_int('ShowDateTime'), 1)

  def test_pinned_stats_accept_minimal_device_state_and_do_not_invent_metrics(self):
    helper = Path(os.environ['CARROT_HELPER_ROOT']).resolve()
    sys.path[:0] = [str(helper / 'tools/jetlink'), str(helper / 'openpilot/selfdrive/carrot/cluster')]
    import hud_stats
    sm = hkg.HkgSubMaster(['deviceState'])
    stats = hud_stats.VehicleSystemStats(sm=sm)
    overlay = hud_stats.VehicleCpuOverlay(sm=sm)
    values = {'started': True, 'deviceType': 'mici'}
    def packet():
      return time.monotonic(), {'hkg': {'deviceState': values}, 'age': {'deviceState': .01}, '_received_epoch': 1}
    with patch.object(hkg, 'snapshot', side_effect=packet):
      result = stats.sample()
      self.assertIsNone(result.cpu_used_percent)
      self.assertIsNone(result.memory_used_percent)
      self.assertIsNone(result.disk_used_percent)
      self.assertEqual(overlay.sample_text(), 'CPU --')
      values.update(cpuUsagePercent=[20., 40.], memoryUsagePercent=30., freeSpacePercent=80.)
      result = stats.sample()
      self.assertEqual(result.cpu_used_percent, 30.)
      self.assertEqual(result.memory_used_percent, 30.)
      self.assertEqual(result.disk_used_percent, 20.)
    with patch.object(hkg, 'snapshot', return_value=None):
      self.assertEqual(overlay.sample_text(), 'CPU --')

  def test_live_source_renders_fields_and_clears_cached_path_lead_and_lfa(self):
    helper = Path(os.environ['CARROT_HELPER_ROOT']).resolve()
    sys.path[:0] = [str(helper), str(helper / 'openpilot/selfdrive/carrot/cluster')]
    import cluster_live
    cereal = types.ModuleType('openpilot.cereal')
    messaging = types.ModuleType('openpilot.cereal.messaging')
    messaging.SubMaster = hkg.HkgSubMaster
    cereal.messaging = messaging
    now = time.monotonic()
    data = {
      'carState': {'vEgo': 20., 'vCruiseCluster': 90., 'leftBlinker': True, 'cruiseState': {'available': True}},
      'deviceState': {'started': True},
      'selfdriveState': {'enabled': False, 'alertSize': 'none'},
      'carControl': {'latActive': True},
      'modelV2': {'position': {'x': [0., 10., 20.], 'y': [0., 0., 0.], 'z': [0., 0., 0.]}},
      'radarState': {'leadOne': {'status': True, 'dRel': 30., 'yRel': 1.5, 'vRel': -2.}},
    }
    def packet(values, generation):
      return now, dict(hkg=values, age=dict.fromkeys(values, .01), _received_epoch=generation)
    with patch.dict(sys.modules, {'openpilot.cereal': cereal, 'openpilot.cereal.messaging': messaging}):
      source = hkg.adapt_live_source(cluster_live)()
      self.addCleanup(source.close)
      with patch.object(hkg, 'snapshot', side_effect=[packet(data, 1), None]) as read:
        state = source.update()
        read.assert_called_once_with()
        self.assertEqual(state.speed_kph, 72.)
        self.assertEqual(state.cruise_kph, 90)
        self.assertTrue(state.lfa_active)
        self.assertEqual(len(state.model_path), 3)
        self.assertEqual(len(state.detected_vehicles), 1)
      remaining = {k: v for k, v in data.items() if k not in ('modelV2', 'radarState', 'carControl')}
      with patch.object(hkg, 'snapshot', return_value=packet(remaining, 2)):
        state = source.update()
        self.assertEqual(state.model_path, ())
        self.assertEqual(state.detected_vehicles, ())
        self.assertFalse(state.lfa_active)
      with patch.object(hkg, 'snapshot', side_effect=[None, packet(data, 3)]) as read:
        state = source.update()
        read.assert_called_once_with()
        self.assertEqual(state.alert.alert_type, 'hkgHudStale')
      with patch.object(hkg, 'snapshot', return_value=packet(data, 3)):
        state = source.update()
        self.assertEqual(state.speed_kph, 72.)
        self.assertTrue(state.lfa_active)
      with patch.object(hkg, 'snapshot', return_value=packet({'deviceState': {'started': False}}, 4)), \
           patch.object(hkg.time, 'strftime', return_value='12:34:56'):
        state = source.update()
        self.assertEqual(state.alert.alert_type, 'hkgHudStandby')
        self.assertIn('12:34:56', state.alert.text2)
        self.assertFalse(state.onroad)
        self.assertFalse(state.lfa_active)
        self.assertEqual(state.model_path, ())
        self.assertEqual(state.detected_vehicles, ())
      with patch.object(hkg, 'snapshot', return_value=packet({'deviceState': {'started': True}}, 5)):
        state = source.update()
        self.assertEqual(state.alert.alert_type, 'hkgHudWaiting')
      with patch.object(hkg, 'snapshot', return_value=None):
        self.assertEqual(source.update().alert.alert_type, 'hkgHudStale')


if __name__ == '__main__':
  unittest.main()
