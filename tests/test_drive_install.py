from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import drive_install as bundle
import mac_install


def ditto(*args, **kwargs):
    assert args[0] == 'ditto'
    shutil.copytree(args[1], args[2])


class DriveInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / 'Jetlink.app'
        self.app.mkdir()
        (self.app / 'version').write_text('old')
        self.new_app = self.root / 'new.app'
        self.new_app.mkdir()
        (self.new_app / 'version').write_text('new')
        self.helper = self.root / 'supervisor.py'
        self.helper.write_text('old supervisor')
        self.new_helper = self.root / 'new-supervisor.py'
        self.new_helper.write_text('new supervisor')
        self.live = self.root / 'cluster_live.py'
        self.live.write_text('original with user changes')
        self.patched = self.root / 'patched.py'
        self.patched.write_text('model path')
        self.backup = self.root / 'backup'

    def tearDown(self):
        self.temp.cleanup()

    def install(self):
        bundle.install_bundle(self.new_app, self.new_helper, self.app, self.helper,
                              self.live, self.patched, self.backup)

    @patch.object(mac_install, 'run', side_effect=ditto)
    def test_bundle_install_and_restore_preserves_original_local_renderer(self, run):
        self.install()
        self.assertEqual(self.live.read_text(), 'model path')
        self.assertEqual((self.app / 'version').read_text(), 'new')
        bundle.restore_bundle(self.backup, self.app, self.helper, self.live)
        self.assertEqual(self.live.read_text(), 'original with user changes')
        self.assertEqual((self.app / 'version').read_text(), 'old')
        self.assertEqual(self.helper.read_text(), 'old supervisor')

    @patch.object(mac_install, 'run', side_effect=ditto)
    def test_renderer_copy_failure_rolls_back_all_three_files(self, run):
        replace = bundle.replace_helper
        def fail(source, dest):
            if source == self.patched:
                raise OSError('simulated renderer copy failure')
            replace(source, dest)
        with patch.object(bundle, 'replace_helper', side_effect=fail):
            with self.assertRaises(OSError): self.install()
        self.assertEqual(self.live.read_text(), 'original with user changes')
        self.assertEqual((self.app / 'version').read_text(), 'old')
        self.assertEqual(self.helper.read_text(), 'old supervisor')

    @patch.object(mac_install, 'run', side_effect=ditto)
    def test_later_renderer_edits_block_whole_bundle_rollback(self, run):
        self.install()
        self.live.write_text('later user edit')
        with self.assertRaises(ValueError):
            bundle.restore_bundle(self.backup, self.app, self.helper, self.live)
        self.assertEqual(self.live.read_text(), 'later user edit')
        self.assertEqual((self.app / 'version').read_text(), 'new')

    @patch.object(mac_install, 'run', side_effect=ditto)
    def test_app_restore_failure_retains_current_renderer(self, run):
        self.install()
        with patch.object(bundle, 'restore_pair', side_effect=OSError('simulated restore failure')):
            with self.assertRaises(OSError):
                bundle.restore_bundle(self.backup, self.app, self.helper, self.live)
        self.assertEqual(self.live.read_text(), 'model path')
        self.assertEqual((self.app / 'version').read_text(), 'new')
