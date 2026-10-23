import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hud_supervisor_test', ROOT / 'AppAutostart/mac_hud_supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def record(kind):
  value = dict(version=1, sent=10., events={}, params={}, valid={}, alive={}, received={}, mono={})
  if kind == 'hkg':
    value.update(source='hkg_hud_v1', hkg={'deviceState': {'started': False}}, age={'deviceState': .1})
  return value


class AutoTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.directory = Path(self.temp.name)
    self.packet = self.directory / 'snapshot.packet'
    self.auto = supervisor.AutoCommand(self.directory, self.packet)
    self.clock = 100.
    clock = patch.object(supervisor.time, 'time', side_effect=lambda: self.clock)
    clock.start()
    self.addCleanup(clock.stop)

  def write(self, kind, stamp=None, value=None):
    stamp = self.clock if stamp is None else stamp
    value = record(kind) if value is None else value
    self.packet.write_bytes(struct.pack('<d', stamp) + json.dumps(value).encode())

  def confirm(self, kind):
    self.write(kind)
    self.auto()
    self.clock += .2
    self.write(kind)
    result = self.auto()
    self.assertEqual(Path(result[-1]).name, 'hkg_hud.py' if kind == 'hkg' else 'hud.py')
    return result

  def test_hkg_empty_cereal_envelope_is_never_mistaken_for_carrot(self):
    self.write('hkg')
    self.assertEqual(supervisor.packet_kind(self.packet), ('hkg', 100.))
    self.assertIsNone(self.auto())
    for _ in range(5):
      self.assertIsNone(self.auto())  # one packet read repeatedly is not confirmation
    self.clock += .2
    self.write('hkg')
    self.assertEqual(Path(self.auto()[-1]).name, 'hkg_hud.py')

  def test_carrot_legacy_and_explicit_source(self):
    self.confirm('carrot')
    value = record('carrot')
    value['source'] = 'carrot_hud_v1'
    self.write('carrot', value=value)
    self.assertEqual(supervisor.packet_kind(self.packet)[0], 'carrot')

  def test_both_directions_switch_and_stale_disconnect_keep_current(self):
    original = self.confirm('hkg')
    self.clock += 2.
    self.assertEqual(self.auto(), original)
    self.packet.unlink()
    self.assertEqual(self.auto(), original)
    carrot = self.confirm('carrot')
    self.clock += 2.
    self.assertEqual(self.auto(), carrot)
    self.confirm('hkg')

  def test_stale_startup_unknown_malformed_and_foreign_sources_do_not_launch(self):
    for stamp in (99., 101., float('nan'), float('inf')):
      self.write('hkg', stamp=stamp)
      self.assertIsNone(self.auto())
    bad_values = [[], {}, dict(record('carrot'), source='other_hud'),
                  dict(record('carrot'), hkg={}), dict(record('carrot'), events=[]),
                  dict(record('carrot'), sent=float('nan')), dict(record('carrot'), version=2),
                  dict(record('hkg'), age=[])]
    for value in bad_values:
      self.write('carrot', value=value)
      self.assertIsNone(self.auto())
    for raw in (b'', b'bad', struct.pack('<d', 100.) + b'not json', b'x' * (96 * 1024 + 9)):
      self.packet.write_bytes(raw)
      self.assertIsNone(self.auto())

  def test_alternating_sources_or_gap_do_not_confirm_a_switch(self):
    original = self.confirm('hkg')
    for kind in ('carrot', 'hkg', 'carrot', 'hkg', 'carrot'):
      self.clock += .1
      self.write(kind)
      self.assertEqual(self.auto(), original)
    self.clock += 1.
    self.assertEqual(self.auto(), original)
    self.write('carrot')
    self.assertEqual(self.auto(), original)
    self.clock += .1
    self.write('carrot')
    self.assertNotEqual(self.auto(), original)

  def test_full_carrot_payload_allowed_but_hkg_limit_retained(self):
    value = record('carrot')
    value['padding'] = 'x' * 20000
    self.write('carrot', value=value)
    self.assertEqual(supervisor.packet_kind(self.packet)[0], 'carrot')
    value.update(source='hkg_hud_v1', hkg={}, age={})
    self.write('hkg', value=value)
    self.assertIsNone(supervisor.packet_kind(self.packet))


class LifecycleTests(unittest.TestCase):
  def test_renderer_group_stops_before_next_owner_and_parent_exit_cleans_up(self):
    ticks = [0.]
    active = []
    actions = []
    def select():
      if ticks[0] < .1:
        return None
      return ['python', 'hkg_hud.py' if ticks[0] < .3 else 'hud.py']
    class Child:
      def __init__(self, command, start_new_session):
        self.command = command
        self.pid = 1234
        assert start_new_session
        assert not active, 'overlapping panel owners'
        active.append(self)
        actions.append(('start', command[-1]))
      def poll(self):
        return None
    def cleanup(child):
      actions.append(('stop', child.command[-1]))
      active.remove(child)
    with tempfile.TemporaryDirectory() as directory, \
         patch.object(supervisor.os, 'getppid', side_effect=lambda: 7 if ticks[0] < .6 else 8), \
         patch.object(supervisor.time, 'sleep', side_effect=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds)), \
         patch.object(supervisor.subprocess, 'Popen', side_effect=Child), \
         patch.object(supervisor, 'terminate_group', side_effect=cleanup):
      self.assertEqual(supervisor.supervise(None, 7, Path(directory), select_command=select), 0)
    self.assertEqual(actions, [('start', 'hkg_hud.py'), ('stop', 'hkg_hud.py'),
                               ('start', 'hud.py'), ('stop', 'hud.py')])
    self.assertFalse(active)


if __name__ == '__main__':
  unittest.main()
