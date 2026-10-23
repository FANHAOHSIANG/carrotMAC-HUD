import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hkg_display', ROOT / 'hkg/hkg_display.py')
display = importlib.util.module_from_spec(spec)
spec.loader.exec_module(display)


class DisplaySettingsTests(unittest.TestCase):
  def test_rotation_and_brightness_reload_and_survive_new_reader(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'settings.json'
      reader = display.DisplaySettings(path)
      with patch.object(display.time, 'monotonic', return_value=10.):
        self.assertEqual(reader.get('ClusterHudOrientation'), b'0')
      display.save_settings({'orientation': 2, 'brightness': 25}, path)
      with patch.object(display.time, 'monotonic', return_value=11.):
        self.assertEqual(reader.get('ClusterHudOrientation'), b'2')
        self.assertEqual(reader.get('ClusterHudBrightness'), b'25')
      self.assertEqual(display.DisplaySettings(path).get('ClusterHudOrientation'), b'2')
      self.assertIsNone(reader.get('IsOnroad'))

  def test_invalid_values_never_replace_saved_preferences(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'settings.json'
      display.save_settings({'orientation': 2}, path)
      before = path.read_bytes()
      for invalid in ({'orientation': 1}, {'orientation': True}, {'brightness': 0}, {'brightness': 101}, {'IsOnroad': 1}):
        with self.assertRaises(ValueError):
          display.save_settings(invalid, path)
        self.assertEqual(path.read_bytes(), before)

  def test_corrupt_file_keeps_last_good_value_without_rotation_loop(self):
    with tempfile.TemporaryDirectory() as directory:
      path = Path(directory) / 'settings.json'
      display.save_settings({'orientation': 2}, path)
      reader = display.DisplaySettings(path)
      with patch.object(display.time, 'monotonic', return_value=10.):
        self.assertEqual(reader.get('ClusterHudOrientation'), b'2')
      path.write_text('{bad')
      with patch.object(display.time, 'monotonic', return_value=11.):
        self.assertEqual(reader.get('ClusterHudOrientation'), b'2')

  def test_native_dialog_cancel_returns_without_saving(self):
    with patch.object(display.sys, 'platform', 'darwin'), patch.object(display.Path, 'is_file', return_value=True), \
         patch.object(display, 'read_settings', return_value=dict(display.DEFAULTS)), \
         patch.object(display, 'choose', return_value=''), patch.object(display, 'save_settings') as save:
      display.main()
      save.assert_not_called()

  def test_native_dialog_maps_180_degrees_to_renderer_orientation_two(self):
    with patch.object(display.sys, 'platform', 'darwin'), patch.object(display.Path, 'is_file', return_value=True), \
         patch.object(display, 'read_settings', side_effect=lambda: dict(display.DEFAULTS)), \
         patch.object(display, 'choose', side_effect=['畫面方向', '旋轉 180°', '結束']), \
         patch.object(display, 'save_settings') as save:
      display.main()
      save.assert_called_once_with({'orientation': 2, 'brightness': 75})


if __name__ == '__main__':
  unittest.main()
