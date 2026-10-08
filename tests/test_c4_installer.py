"""Exercise actual git apply, backups and cancellation against official fixtures."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('c4_installer', REPO / 'scripts/install_c4_parked.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@unittest.skipUnless(os.environ.get('C4_BASELINE_ROOT'), 'Official C4 fixtures are supplied by check_c4_parked.py')
class InstallerTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
    self.directory = Path(self.temp.name)
    self.root = self.directory / 'source'
    shutil.copytree(os.environ['C4_BASELINE_ROOT'], self.root)
    self.state, self.flag, self.params = (self.directory / name for name in ('state', 'flag', 'params'))
    self.params.mkdir()
    (self.params / 'IsOffroad').write_bytes(b'1'); (self.params / 'IsOnroad').write_bytes(b'0')
    installer.run('git', '-C', self.root, 'init', '-q')
    installer.run('git', '-C', self.root, 'add', '.')
    installer.run('git', '-C', self.root, '-c', 'user.name=tests', '-c', 'user.email=tests@local', 'commit', '-qm', 'baseline')
    self.original = {name: (self.root / name).read_bytes() for name in installer.FILES[:-1]}

  def assert_original(self):
    self.assertFalse(self.flag.exists())
    self.assertFalse((self.root / installer.FILES[-1]).exists())
    for name, content in self.original.items(): self.assertEqual((self.root / name).read_bytes(), content)

  def install(self, **kwargs):
    with patch.object(installer, 'revision', lambda root: installer.BASE):
      installer.install(self.root, self.state, self.flag, self.params, **kwargs)

  def test_install_cpu_checks_and_exact_restore(self):
    self.install()
    self.assertTrue(self.flag.exists()); self.assertTrue((self.root / installer.FILES[-1]).exists())
    installer.restore(self.root, self.state, self.flag)
    self.assert_original()

  def test_check_only_does_not_install(self):
    self.install(check_only=True)
    self.assert_original(); self.assertFalse(self.state.exists())

  def test_ignition_on_rejected_before_any_write(self):
    (self.params / 'IsOnroad').write_bytes(b'1')
    with self.assertRaises(ValueError): self.install()
    self.assert_original(); self.assertFalse(self.state.exists())

  def test_wrong_commit_rejected_before_any_write(self):
    with self.assertRaises(ValueError): installer.install(self.root, self.state, self.flag, self.params)
    self.assert_original(); self.assertFalse(self.state.exists())

  def test_existing_local_edit_is_preserved(self):
    target = self.root / installer.FILES[0]
    changed = target.read_bytes() + b'\n# existing custom edit\n'; target.write_bytes(changed)
    with self.assertRaises(ValueError): self.install()
    self.assertEqual(target.read_bytes(), changed); self.assertFalse(self.flag.exists())

  def test_failed_cpu_check_restores_before_enable(self):
    actual = installer.run
    def run(*args, **kwargs):
      if str(args[0]) == sys.executable: raise subprocess.CalledProcessError(1, 'CPU checks')
      return actual(*args, **kwargs)
    with patch.object(installer, 'run', run), self.assertRaises(subprocess.CalledProcessError): self.install()
    self.assert_original()

  def test_ignition_transition_during_validation_restores_before_enable(self):
    actual = installer.run
    def run(*args, **kwargs):
      if str(args[0]) == sys.executable:
        (self.params / 'IsOnroad').write_bytes(b'1')
        return subprocess.CompletedProcess(args, 0)
      return actual(*args, **kwargs)
    with patch.object(installer, 'run', run), self.assertRaises(ValueError): self.install()
    self.assert_original()


if __name__ == '__main__':
  unittest.main()
