import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('updater', Path(__file__).resolve().parents[1] / 'scripts/mac_install.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def ditto(*args, **kwargs):
    assert args[0] == 'ditto'
    shutil.copytree(args[1], args[2])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / 'Jetlink.app'
        self.app.mkdir()
        (self.app / 'version').write_text('old')
        self.helper = self.root / 'helper.py'
        self.helper.write_text('old helper')
        self.new_app = self.root / 'new.app'
        self.new_app.mkdir()
        (self.new_app / 'version').write_text('new')
        self.new_helper = self.root / 'new.py'
        self.new_helper.write_text('new helper')
        self.backup = self.root / 'backup'

    def tearDown(self):
        self.temp.cleanup()

    @patch.object(updater, 'run', side_effect=ditto)
    def test_install_and_restore_matched_pair(self, run):
        updater.install_pair(self.new_app, self.new_helper, self.app, self.helper, self.backup)
        self.assertEqual((self.app / 'version').read_text(), 'new')
        self.assertEqual(self.helper.read_text(), 'new helper')
        updater.restore_pair(self.backup, self.app, self.helper)
        self.assertEqual((self.app / 'version').read_text(), 'old')
        self.assertEqual(self.helper.read_text(), 'old helper')

    @patch.object(updater, 'run', side_effect=ditto)
    def test_helper_failure_rolls_back_app(self, run):
        real_replace = updater.replace_helper
        def replace(source, target):
            if source == self.new_helper:
                raise OSError('simulated copy failure')
            real_replace(source, target)
        with patch.object(updater, 'replace_helper', side_effect=replace):
            with self.assertRaises(OSError):
                updater.install_pair(self.new_app, self.new_helper, self.app, self.helper, self.backup)
        self.assertEqual((self.app / 'version').read_text(), 'old')
        self.assertEqual(self.helper.read_text(), 'old helper')

    @patch.object(updater, 'run', side_effect=ditto)
    def test_restore_v1_without_supervisor(self, run):
        self.helper.unlink()
        updater.install_pair(self.new_app, self.new_helper, self.app, self.helper, self.backup)
        updater.restore_pair(self.backup, self.app, self.helper)
        self.assertFalse(self.helper.exists())
        self.assertEqual((self.app / 'version').read_text(), 'old')



if __name__ == '__main__':
    unittest.main()
