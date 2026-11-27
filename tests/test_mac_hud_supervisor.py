import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

source = Path(__file__).resolve().parents[1] / 'AppAutostart/mac_hud_supervisor.py'
spec = importlib.util.spec_from_file_location('supervisor', source)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


class SupervisorTests(unittest.TestCase):
    def test_normal_cleanup(self):
        child = Mock(pid=2345)
        with patch.object(supervisor, '_terminate_group') as clean:
            self.assertTrue(supervisor.terminate_group(child))
            clean.assert_called_once_with(child, 2.)

    def test_denied_but_group_absent(self):
        child = Mock(pid=2345, **{'poll.return_value': 0})
        with patch.object(supervisor, '_terminate_group', side_effect=PermissionError), \
             patch.object(supervisor.subprocess, 'run', return_value=Mock(stdout='1\n42\n')):
            self.assertTrue(supervisor.terminate_group(child))
            child.terminate.assert_not_called()

    def test_denied_group_still_exists(self):
        child = Mock(pid=2345, **{'poll.return_value': 0})
        with patch.object(supervisor, '_terminate_group', side_effect=PermissionError), \
             patch.object(supervisor.subprocess, 'run', return_value=Mock(stdout='1\n2345\n')):
            self.assertFalse(supervisor.terminate_group(child))

    def test_process_table_unavailable(self):
        with patch.object(supervisor.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ps', 2)):
            self.assertFalse(supervisor.group_absent(2345))

    def test_denied_live_child_direct_cleanup(self):
        child = Mock(pid=2345, **{'poll.side_effect': [None, 0]})
        with patch.object(supervisor, '_terminate_group', side_effect=PermissionError), \
             patch.object(supervisor, 'group_absent', return_value=True):
            self.assertTrue(supervisor.terminate_group(child))
            child.terminate.assert_called_once()

    def test_unverified_cleanup_stops_restart(self):
        child = Mock(pid=2345, **{'poll.return_value': 0})
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(supervisor.os, 'getppid', return_value=42), \
             patch.object(supervisor.subprocess, 'Popen', return_value=child) as start, \
             patch.object(supervisor, 'terminate_group', return_value=False) as clean:
            path = Path(directory)
            (path / 'status.json').write_text('{}')
            self.assertEqual(supervisor.supervise(['hud'], 42, path), 75)
            start.assert_called_once()
            clean.assert_called_once_with(child)
            self.assertFalse((path / 'status.json').exists())


if __name__ == '__main__':
    unittest.main()
