import sys
import unittest
from unittest.mock import MagicMock, patch


class IconLayoutTest(unittest.TestCase):
    def test_all_classes_remain_visible_beside_lead_text(self):
        # Drawing runs in the helper process. The placement check needs no GPU.
        with patch.dict(sys.modules, pyray=MagicMock()):
            import mac_vision_icons as layout

        classes = ("person", "motorcycle", "bicycle", "cone", "car", "bus", "truck", "crosswalk")
        self.assertEqual(set(classes), set(layout.ICON_COLORS))
        side = 36
        room = (60, 40, 800, 420)
        text = (375, 175, 90, 50)
        anchors = [(kind, 420., 200.) for kind in classes]
        anchors.append(("car", -300., 45.))
        with patch.object(layout, "rl", MagicMock()), patch.object(layout, "draw_object_icon") as draw:
            self.assertEqual(layout.draw_class_icons(anchors, room, side, [text]), len(classes))
        glyphs = [call.args for call in draw.call_args_list]
        self.assertEqual([g[0] for g in glyphs], list(classes))
        for i, (_, x, y, _) in enumerate(glyphs):
            self.assertTrue(room[0] <= x-side/2 < x+side/2 <= room[2])
            self.assertTrue(room[1] <= y-side/2 < y+side/2 <= room[3])
            self.assertTrue(x+side/2 < text[0] or x-side/2 > text[0]+text[2] or
                            y+side/2 < text[1] or y-side/2 > text[1]+text[3])
            for _, px, py, _ in glyphs[:i]:
                self.assertGreaterEqual(max(abs(px-x), abs(py-y)), side)
