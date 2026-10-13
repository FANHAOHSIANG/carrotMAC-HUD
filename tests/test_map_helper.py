from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import map_helper
import mac_install


class MapHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.helper = self.root / 'helper'
        self.stage = self.root / 'stage'
        self.backup = self.root / 'backup'
        self.backup.mkdir()
        for name in map_helper.FILES:
            new = self.stage / name
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_text('new')
        for name in map_helper.FILES[:2]:
            old = self.helper / name
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text('old')

    def tearDown(self):
        self.temp.cleanup()

    def test_restore_preserves_old_renderer_and_removes_new_receiver(self):
        map_helper.install_map_helper(self.stage, self.helper, self.backup)
        self.assertTrue((self.helper / map_helper.FILES[2]).exists())
        map_helper.restore_map_helper(self.helper, self.backup)
        for name in map_helper.FILES[:2]:
            self.assertEqual((self.helper / name).read_text(), 'old')
        self.assertFalse((self.helper / map_helper.FILES[2]).exists())

    def test_partial_helper_install_restores_all_modified_files(self):
        replace = mac_install.replace_helper
        def fail_second(source, target):
            if source == self.stage / map_helper.FILES[1]:
                raise OSError('simulated renderer replacement failure')
            return replace(source, target)
        with patch.object(mac_install, 'replace_helper', side_effect=fail_second):
            with self.assertRaises(OSError):
                map_helper.install_map_helper(self.stage, self.helper, self.backup)
        for name in map_helper.FILES[:2]:
            self.assertEqual((self.helper / name).read_text(), 'old')
        self.assertFalse((self.helper / map_helper.FILES[2]).exists())


if __name__ == '__main__':
    unittest.main()
