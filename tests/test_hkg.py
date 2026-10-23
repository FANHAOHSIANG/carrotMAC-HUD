import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP_BYTES = b'original app carrot_hud_v1 mac_hud_supervisor.py'
spec = importlib.util.spec_from_file_location('hkg_hud', ROOT / 'hkg/hkg_hud.py')
hkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hkg)
spec = importlib.util.spec_from_file_location('enable_hkg', ROOT / 'scripts/enable_hkg.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def record():
  return dict(version=1, source='hkg_hud_v1', sent=20., hkg={'carState': {'vEgo': 20., 'leftBlinker': True},
              'carControl': {'latActive': True}}, age={'carState': .1, 'carControl': .1}, params={})


class ReaderTests(unittest.TestCase):
  def packet(self, folder, value, stamp=100.):
    path = Path(folder) / 'snapshot.packet'
    path.write_bytes(hkg.HEADER.pack(stamp) + json.dumps(value).encode())
    return path

  def test_host_epoch_converted_to_local_monotonic(self):
    with tempfile.TemporaryDirectory() as folder:
      path = self.packet(folder, record())
      received, data = hkg.read_packet(path, epoch=100.1, mono=30.)
      self.assertAlmostEqual(received, 29.9)
      self.assertAlmostEqual(data['age']['carState'], .2)

  def test_stale_future_wrong_source_and_oversize_rejected(self):
    with tempfile.TemporaryDirectory() as folder:
      for stamp in (99., 101., float('nan')):
        self.assertIsNone(hkg.read_packet(self.packet(folder, record(), stamp), epoch=100., mono=30.))
      data = record()
      data['source'] = 'carrot'
      self.assertIsNone(hkg.read_packet(self.packet(folder, data), epoch=100., mono=30.))
      data = record()
      data['extra'] = 'x' * hkg.MAX_BYTES
      self.assertIsNone(hkg.read_packet(self.packet(folder, data), epoch=100., mono=30.))

  def test_source_staleness_expires_before_whole_packet(self):
    with tempfile.TemporaryDirectory() as folder:
      data = record()
      data['age']['carState'] = .45
      result = hkg.read_packet(self.packet(folder, data), epoch=100.1, mono=30.)
      self.assertNotIn('carState', result[1]['hkg'])
      self.assertIn('carControl', result[1]['hkg'])

  def test_missing_snapshot_invalidates_all_services_and_recovery_updates(self):
    sm = hkg.HkgSubMaster(['carState', 'carControl', 'carrotMan'])
    data = dict(record(), _received_epoch=100.)
    with patch.object(hkg, 'snapshot', return_value=(30., data)):
      sm.update()
      self.assertEqual(sm['carState'].vEgo, 20.)
      self.assertTrue(sm['carControl'].latActive)
      self.assertFalse(sm.alive['carrotMan'])
      sm.update()
      self.assertFalse(sm.updated['carState'])
    with patch.object(hkg, 'snapshot', return_value=None):
      sm.update()
      self.assertFalse(any(sm.alive.values()))
      self.assertFalse(hasattr(sm['carControl'], 'latActive'))
    with patch.object(hkg, 'snapshot', return_value=(30., data)):
      sm.update()
      self.assertTrue(sm.updated['carState'])


class InstallTests(unittest.TestCase):
  def setup_tree(self, base):
    helper = base / 'carrot/tools/jetlink'
    helper.mkdir(parents=True)
    (helper / 'hud.py').write_text('# if not MAC: panel.lock')
    (helper / 'hud_runtime.py').write_text('PACKET = None')
    (helper / 'mac_hud_supervisor.py').write_text('original supervisor')
    app = base / 'jetlink/macos/build/Jetlink.app/Contents/MacOS/Jetlink'
    app.parent.mkdir(parents=True)
    app.write_bytes(APP_BYTES)
    (base / 'update').mkdir()
    return helper, app

  def test_install_and_restore_preserve_app_and_original_helper(self):
    with tempfile.TemporaryDirectory() as folder:
      base = Path(folder)
      helper, app = self.setup_tree(base)
      with patch.object(installer.subprocess, 'check_output', return_value='a564ce1dc082909b1fdc73b72e64d920336b34d6'):
        installer.install(ROOT, base)
      self.assertTrue((helper / 'hkg-hud.enabled').exists())
      self.assertEqual(app.read_bytes(), APP_BYTES)
      info = json.loads((base / 'update/hkg-hud-backup.json').read_text())
      installer.restore_files(helper, Path(info['backup']), info['existed'])
      self.assertEqual((helper / 'mac_hud_supervisor.py').read_text(), 'original supervisor')
      self.assertFalse((helper / 'hkg_hud.py').exists())

  def test_receiver_writer_and_autostart_allow_existing_app_without_capability_literal(self):
    with tempfile.TemporaryDirectory() as folder:
      base = Path(folder)
      helper, app = self.setup_tree(base)
      data = b'installed 0.8.7 CarrotHUD carrot-hud-writer mac_hud_supervisor.py'
      app.write_bytes(data)
      self.assertNotIn(b'carrot_hud_v1', data)
      with patch.object(installer.subprocess, 'check_output', return_value='a564ce1dc082909b1fdc73b72e64d920336b34d6'):
        installer.install(ROOT, base)
      self.assertEqual(app.read_bytes(), data)
      self.assertTrue((helper / 'hkg-hud.enabled').exists())
      info = json.loads((base / 'update/hkg-hud-backup.json').read_text())
      self.assertEqual(info['app_hud_evidence'], 'receiver class + writer thread')
      installer.restore_files(helper, Path(info['backup']), info['existed'])
      self.assertEqual((helper / 'mac_hud_supervisor.py').read_text(), 'original supervisor')
      self.assertFalse((helper / 'hkg-hud.enabled').exists())

  def test_partial_receiver_or_missing_autostart_aborts_before_backup_or_edit(self):
    for data in (b'CarrotHUD mac_hud_supervisor.py', b'carrot-hud-writer mac_hud_supervisor.py',
                 b'CarrotHUD carrot-hud-writer', b'carrot_hud_v1', b'mac_hud_supervisor.py'):
      with self.subTest(data=data), tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        helper, app = self.setup_tree(base)
        app.write_bytes(data)
        with patch.object(installer.subprocess, 'check_output', return_value='a564ce1dc082909b1fdc73b72e64d920336b34d6'):
          with self.assertRaises(ValueError):
            installer.install(ROOT, base)
        self.assertFalse((base / 'backups').exists())
        self.assertFalse((helper / 'hkg_hud.py').exists())
        self.assertEqual(app.read_bytes(), data)
        self.assertEqual((helper / 'mac_hud_supervisor.py').read_text(), 'original supervisor')

  def test_wrong_renderer_or_official_app_aborts_before_edit(self):
    with tempfile.TemporaryDirectory() as folder:
      base = Path(folder)
      helper, app = self.setup_tree(base)
      with patch.object(installer.subprocess, 'check_output', return_value='new-version'):
        with self.assertRaises(ValueError):
          installer.install(ROOT, base)
      app.write_bytes(b'official app')
      with patch.object(installer.subprocess, 'check_output', return_value='a564ce1dc082909b1fdc73b72e64d920336b34d6'):
        with self.assertRaises(ValueError):
          installer.install(ROOT, base)
      self.assertEqual((helper / 'mac_hud_supervisor.py').read_text(), 'original supervisor')

  def test_reinstall_retains_original_backup_and_failed_upgrade_preserves_working_files(self):
    with tempfile.TemporaryDirectory() as folder:
      base = Path(folder)
      helper, app = self.setup_tree(base)
      with patch.object(installer.subprocess, 'check_output', return_value='a564ce1dc082909b1fdc73b72e64d920336b34d6'):
        installer.install(ROOT, base)
        manifest = base / 'update/hkg-hud-backup.json'
        original = json.loads(manifest.read_text())
        installer.install(ROOT, base)
        updated = json.loads(manifest.read_text())
        self.assertEqual(updated['backup'], original['backup'])
        self.assertNotEqual(updated['last_update_backup'], original['backup'])
        saved = {name: (helper / name).read_bytes() for name in installer.NAMES}
        manifest_before = manifest.read_bytes()
        copy = installer.atomic_copy
        def fail(source, target):
          if source == ROOT / 'hkg/hkg_display.py':
            raise OSError('disk full')
          copy(source, target)
        with patch.object(installer, 'atomic_copy', side_effect=fail), self.assertRaises(OSError):
          installer.install(ROOT, base)
        self.assertEqual(manifest.read_bytes(), manifest_before)
        self.assertEqual({name: (helper / name).read_bytes() for name in installer.NAMES}, saved)
        installer.restore_files(helper, Path(updated['backup']), updated['existed'])
        self.assertEqual((helper / 'mac_hud_supervisor.py').read_text(), 'original supervisor')
        self.assertFalse((helper / 'hkg_display.py').exists())
        self.assertEqual(app.read_bytes(), APP_BYTES)

  def test_failed_write_restores_previous_files(self):
    with tempfile.TemporaryDirectory() as folder:
      base = Path(folder)
      helper, app = self.setup_tree(base)
      real = installer.atomic_copy
      def fail(source, target):
        if source == ROOT / 'AppAutostart/mac_hud_supervisor.py':
          raise OSError('disk full')
        real(source, target)
      with patch.object(installer.subprocess, 'check_output', return_value='a564ce1dc082909b1fdc73b72e64d920336b34d6'), patch.object(installer, 'atomic_copy', side_effect=fail):
        with self.assertRaises(OSError):
          installer.install(ROOT, base)
      self.assertFalse((helper / 'hkg_hud.py').exists())
      self.assertEqual((helper / 'mac_hud_supervisor.py').read_text(), 'original supervisor')


if __name__ == '__main__':
  unittest.main()
