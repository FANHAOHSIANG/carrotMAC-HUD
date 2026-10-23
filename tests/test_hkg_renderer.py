"""Optional integration test against the real pinned Carrot parser/live source.

CARROT_HELPER_ROOT=/path/to/carrot python3 -m unittest discover -s tests -p test_hkg_renderer.py -v
No GPU, USB, vehicle data or control processes are used.
"""
import importlib.util
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


if __name__ == '__main__':
  unittest.main()
