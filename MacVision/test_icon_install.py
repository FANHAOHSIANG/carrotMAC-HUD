from pathlib import Path
import tempfile
import unittest

from install import CAPTURE_KEY, CAMERA_KEY, REL, receiver_update, set_frame_reset, write_file


class CameraTextureKeyTests(unittest.TestCase):
    def test_both_known_receivers_keep_source_clock_provenance_and_roll_back_exactly(self):
        for key in (CAMERA_KEY, CAPTURE_KEY):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path = root / "tools/jetlink/hud_camera.py"
                dest = root / REL
                path.parent.mkdir(parents=True)
                source = "def texture_key(name, frame):\n" + key + "    return key\n"
                path.write_text(source)
                write_file(*receiver_update(dest, False))
                self.assertIsNone(receiver_update(dest, False))
                namespace = {}
                exec(compile(path.read_text(), str(path), "exec"), namespace)
                key_for = namespace["texture_key"]
                self.assertEqual(key_for('road', {'frame': 12, 'time': 9.}), ('road', 12, 9., 'preview'))
                self.assertEqual(key_for('road', {'frame': 12, 'time': 9., 'capture_time': 8.5}),
                                 ('road', 12, 8.5, 'capture'))
                write_file(*receiver_update(dest, True))
                self.assertEqual(path.read_text(), source)
                self.assertIsNone(receiver_update(dest, True))

    def test_custom_texture_receiver_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "tools/jetlink/hud_camera.py"
            path.parent.mkdir(parents=True)
            path.write_text("def texture_key(name, frame):\n    return ('other', name)\n")
            self.assertIsNone(receiver_update(root / REL, False))
            self.assertIsNone(receiver_update(root / REL, True))


class FrameResetTests(unittest.TestCase):
    def test_render_resets_feedback_before_map_or_gear_early_exit(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        source = ('class ClusterUiRenderer:\n'
                  '    def render(self, mode):\n'
                  '        """My installed HUD overlay."""\n'
                  '        if mode in ("map", "park"):\n'
                  '            return\n'
                  '        events.append("world")\n')
        updated = set_frame_reset(source, False)
        self.assertEqual(set_frame_reset(updated, False), updated)
        self.assertEqual(set_frame_reset(updated, True), source)
        events = []
        env = {"events": events}
        exec(updated, env)
        renderer = env["ClusterUiRenderer"]()
        self.assertEqual(renderer.render.__doc__, "My installed HUD overlay.")
        with patch.dict(sys.modules, mac_vision_overlay=SimpleNamespace(begin_frame=lambda: events.append("reset"))):
            for mode in ("drive", "map", "park"):
                renderer.render(mode)
        self.assertEqual(events, ["reset", "world", "reset", "reset"])
