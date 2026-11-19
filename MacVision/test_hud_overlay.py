import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import mac_vision_overlay as overlay
from preview import hud_feedback


class OverlayTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "vision.json"
        self.epoch = 1794999000.
        self.rl = MagicMock()
        for target, value in ((overlay, {"RESULT": self.path, "_last_report": 0., "_scene_feedback": None}),
                              (overlay.time, {"time": lambda: self.epoch, "monotonic": lambda: 75.})):
            ctx = patch.multiple(target, **value)
            ctx.start()
            self.addCleanup(ctx.stop)
        ctx = patch.dict("sys.modules", pyray=self.rl)
        ctx.start()
        self.addCleanup(ctx.stop)
        self.proj = NS(view_from_road=((0,-1,0),(0,0,-1),(1,0,0)), camera_height_m=1.3,
                       focal_length=500, camera_width=1000, camera_height=500, wide_camera=False)
        self.renderer = NS(_camera_overlay_projection=lambda state: self.proj, camera_overlay_z_offset_m=.1)
        self.state = NS(camera_calibration_euler=(0.,0.,0.), road_transform_trans=(0,0,1.3))
        self.items = [["person", .6, .7, .04, .12], ["crosswalk", .5,.7,.3,.08]]
        self.write(.25)

    def write(self, age):
        self.path.write_text(json.dumps([self.epoch-age, self.items]))

    def frame(self):
        overlay.draw(self.renderer, self.state, 0., 4.)
        overlay.draw_detection_notice(0)
        self.assertIsNone(overlay._scene_feedback)
        return hud_feedback(self.path.parent)

    def test_live_mixed_frame(self):
        self.assertAlmostEqual(overlay.location(self.proj,.6,.7,.1)[1],6.)
        self.assertEqual(self.frame(), "HUD 3D: 2 | projected")
        self.rl.draw_sphere.assert_called_once()
        self.assertEqual(self.rl.draw_cube.call_count, 5)
        self.rl.draw_text.assert_called_once()

    def test_calibration_missing(self):
        self.state.camera_calibration_euler=None
        self.assertIn("no camera calibration",self.frame())
        self.rl.draw_sphere.assert_not_called()
        self.rl.draw_text.assert_called_once()

    def test_shifted_native_vehicle_matches_in_road_coordinates(self):
        overlay._matches.reset()
        self.items = [["car", .5, .7, .15, .15]]
        native = [NS(center=NS(x=-2., y=10.))]
        for age, expected in ((.35, 1), (.15, 0)):
            self.write(age)
            overlay.draw(self.renderer, self.state, 2., 4., native)
            self.assertEqual(overlay._scene_feedback[1], expected)
        self.assertIn("matched 1 native", overlay._scene_feedback[2])

    def test_confirmed_motorcycle_replaces_only_its_native_marker(self):
        overlay._matches.reset()
        self.items = [["motorcycle", .5, .7, .14, .17]]
        v = NS(center=NS(x=-2., y=10.), source="radarState", confidence=.8,
               right_x=1., right_y=0., forward_x=0., forward_y=1.,
               body_color=(245,180,35), rear_color=(240,155,30))
        neighbor = NS(center=NS(x=1.4, y=10.))
        for age, expected in ((.34, set()), (.34, set()), (.14, {1}), (1., set())):
            self.write(age)
            self.assertEqual(overlay.draw(self.renderer, self.state, 2., 4., [neighbor, v]), expected)
        self.rl.Color.assert_any_call(245,180,35,200)
        self.rl.Vector3.assert_any_call(-2., 9.61, .81)

    def test_height_missing(self):
        self.state.road_transform_trans=None
        self.assertIn("2 | estimated height",self.frame())

    def test_stale(self):
        self.write(1.)
        self.assertIn("0 | result expired",self.frame())
        self.rl.draw_text.assert_not_called()
        self.rl.draw_sphere.assert_not_called()

    def test_future_clock(self):
        self.write(-2.)
        self.assertIn("0 | result expired",self.frame())

    def test_other_view(self):
        overlay.draw_detection_notice(1200)
        self.assertIn("0 | 2D view",hud_feedback(self.path.parent))
        self.rl.draw_text.assert_called_once()

    def test_no_hud(self):
        self.assertEqual(hud_feedback(self.path.parent),"HUD: awaiting renderer")


class VehicleMatchTest(unittest.TestCase):
    def test_unique_vehicle_requires_second_capture(self):
        m = overlay.VehicleMatches()
        pts = [('car', .2, 18), ('truck', 3.4, 18), ('person', .2, 18)]
        for stamp, expected in ((8., {}), (8., {}), (8.2, {0:0}), (9., {})):
            self.assertEqual(m.match(stamp, pts, [(0, 18.5)]), expected)

    def test_ambiguous_pairs_and_disappearing_targets(self):
        m = overlay.VehicleMatches()
        p = [('car', 0, 16)]
        m.match(1, p, [(0, 16)])
        self.assertEqual(m.match(1.2, p*2, [(0, 16)]), {})
        self.assertEqual(m.match(1.4, p, [(0, 16), (.3, 16)]), {})
        self.assertEqual(m.match(1.6, p, []), {})


class NativeCarTest(unittest.TestCase):
    def test_body_uses_native_pose_and_color(self):
        v = NS(width_m=2., length_m=4., height_m=1.5, confidence=.5,
               center=NS(x=3., y=10.), right_x=0., right_y=-1., forward_x=1., forward_y=0.,
               rear_color=(255,170,30), side_color=(211,130,20), body_color=(255,195,50))
        renderer = MagicMock()
        overlay.draw_native_car(renderer, v, lambda *xyz: xyz)
        renderer._draw_vehicle_shadow.assert_called_once_with(v)
        faces = [call.args for call in renderer._draw_quad.call_args_list]
        self.assertEqual(len(faces), 10)
        self.assertEqual(faces[0][-1], (*v.rear_color,155))
        self.assertEqual(faces[4][0], (1.,11.,.035+.53*1.5))
        self.assertGreater(faces[-1][0][2], faces[4][0][2])
