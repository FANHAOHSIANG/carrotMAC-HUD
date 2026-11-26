import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import mac_vision_overlay as overlay


class VisionIconTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "vision.json"
        self.now = 1000.
        self.place = MagicMock(side_effect=lambda anchors, *_: len(anchors))
        self.project = MagicMock(side_effect=lambda p, *_: NS(x=p[0], y=p[1]))
        self.rl = MagicMock()
        self.rl.Vector3.side_effect = lambda *args: args
        for ctx in (
            patch.object(overlay, "RESULT", self.path),
            patch.object(overlay, "_matches", overlay.VehicleMatches()),
            patch.object(overlay, "_scene_feedback", None),
            patch.object(overlay, "_placed_icons", None),
            patch.object(overlay.time, "time", lambda: self.now),
            patch.dict("sys.modules", pyray=self.rl, cluster_config=NS(DESIGN_HEIGHT=480),
                       cluster_scene=NS(render_scene_forward_m=lambda d, state: 4 + d * .5),
                       cluster_renderer=NS(world_to_screen_label_anchor=self.project),
                       mac_vision_icons=NS(draw_class_icons=self.place)),
        ):
            ctx.start()
            self.addCleanup(ctx.stop)
        rect = NS(x=0, y=0, width=800, height=400)
        self.proj = NS(wide_camera=False, dest=rect, video_dest=rect, view_from_road=((0,-1,0),(0,0,-1),(1,0,0)),
                       camera_height_m=1.3, focal_length=500, camera_width=1000, camera_height=500)
        self.renderer = NS(width=1920, height=480, camera_overlay_z_offset_m=.1,
                           _camera_overlay_projection=lambda state: self.proj)
        self.state = NS(onroad=True, camera_calibration_euler=(0.,0.,0.), road_transform_trans=(0,0,1.3))
        self.bounds = (0, 0, 800, 400)
        self.metrics = [(20, 30, 90, 12)]
        self.rows = [["car", .6, .7, .1, .14], ["person", .6, .7, .06, .15], ["crosswalk", .5, .7, .30, .08]]
        self.frame = ("road", 12, 52., "capture")

    def write(self, age, rows):
        self.path.write_text(json.dumps([self.now - age, rows]))

    def film(self, **fields):
        packet = dict(version=2, camera="road", frame_id=12, source_time=52., time_kind="capture",
                      stamp=self.now - .2, objects=self.rows)
        packet.update(fields)
        self.path.with_name("vision-frame.json").write_text(json.dumps(packet))

    def test_native_car_confirms_at_measured_position_without_duplicate_body(self):
        self.write(.2, self.rows[:1])
        native = NS(center=NS(x=-.4), longitudinal_m=6., relative_speed_mps=0.)
        with patch.object(overlay, "location", return_value=(.8, 6.)):
            overlay.draw(self.renderer, self.state, 1.5, 4., [native])
        self.rl.draw_cube.assert_not_called()
        self.assertTrue(overlay.has_scene_icons(self.renderer))
        self.assertEqual(overlay.draw_scene_icons(self.renderer, self.state, "cam", self.bounds, self.metrics), 1)
        self.place.assert_called_once_with([("car", .8, 7.)], self.bounds, 36, self.metrics)
        self.assertFalse(overlay.has_scene_icons(self.renderer))
        with patch.object(overlay, "report_drawn") as report:
            overlay.draw_detection_notice(0)
        self.assertEqual(report.call_args.args[0], 0)
        self.assertIn("matched 1 native", report.call_args.args[1])
        self.assertTrue(report.call_args.args[1].endswith(" | icons 1"))
        self.assertEqual(self.rl.draw_text.call_args.args[0], "ROAD 1")

    def test_unconfirmed_standalone_respects_distinct_capture_gate(self):
        for age, expected in ((.40, False), (.40, False), (.15, True)):
            self.write(age, self.rows[:1])
            overlay.draw(self.renderer, self.state, 0., 4.)
            self.assertEqual(overlay.has_scene_icons(self.renderer), expected)
        self.now += 1.
        self.assertEqual(overlay.draw_scene_icons(self.renderer, self.state, "cam", self.bounds), 0)
        self.place.assert_not_called()

    def test_scene_clears_old_icons_and_keeps_unprojectable_classes_in_legend(self):
        self.write(.2, self.rows[1:])
        overlay.draw(self.renderer, self.state, 0., 4.)
        self.assertTrue(overlay.has_scene_icons(self.renderer))
        with patch.object(overlay, "outside_road", return_value=True):
            overlay.draw(self.renderer, self.state, 0., 4.)
        self.assertFalse(overlay.has_scene_icons(self.renderer))
        self.assertEqual(overlay._scene_feedback[0], self.rows[1:])
        self.state.camera_calibration_euler = None
        overlay.draw(self.renderer, self.state, 0., 4.)
        self.assertFalse(overlay.has_scene_icons(self.renderer))

    def test_film_uses_exact_or_proven_forward_capture_and_visible_crop(self):
        self.film(objects=self.rows[:2] + [["crosswalk", .5, .47, .30, .16]])
        self.proj.video_dest = NS(x=0, y=-260, width=800, height=600)
        for frame in (self.frame, ("road", 17, 52.25, "capture")):
            self.assertTrue(overlay.has_camera_icons(self.renderer, frame))
            self.assertEqual(overlay.draw_camera_icons(self.renderer, self.state, self.proj, frame, self.metrics), 3)
            anchors, bounds, size, metrics = self.place.call_args.args
            self.assertEqual((bounds, size, metrics), (self.bounds, 36., self.metrics))
            self.assertEqual([(kind, round(x), round(y)) for kind, x, y in anchors],
                             [("car", 480, 76), ("person", 480, 70), ("crosswalk", 400, 0)])

    def test_film_declines_unproven_provenance_expiry_and_bad_boxes(self):
        self.film()
        for frame in (None, ("road", 12), ("wide", 12, 52., "capture"), ("road", 12, 52.01, "capture"),
                      ("road", 10, 52.1, "capture"), ("road", 13, 52.26, "capture"),
                      ("road", 13, 51.99, "capture"), ("road", 12, 52., "preview")):
            self.assertFalse(overlay.has_camera_icons(self.renderer, frame), frame)
        self.film(time_kind="preview")
        self.assertTrue(overlay.has_camera_icons(self.renderer, ("road", 12, 52., "preview")))
        self.assertFalse(overlay.has_camera_icons(self.renderer, ("road", 13, 52.12, "preview")))
        self.film(objects=[["unknown", .6, .7, .1, .1], ["person", .6, .7, 0, .1]])
        self.assertFalse(overlay.has_camera_icons(self.renderer, self.frame))
        self.film()
        self.now += 1.
        self.assertFalse(overlay.has_camera_icons(self.renderer, self.frame))

    def test_film_feedback_reports_painted_icons_only_and_resets_next_frame(self):
        self.film()
        self.place.side_effect = lambda *_: 2
        with patch.object(overlay, "report_drawn") as report:
            overlay.draw_camera_icons(self.renderer, self.state, self.proj, self.frame)
            overlay.draw_detection_notice(0)
            report.assert_called_with(0, "2D view | icons 2")
            self.assertEqual(self.rl.draw_text.call_args.args[0], "ROAD 2")
            overlay.draw_camera_icons(self.renderer, self.state, self.proj, self.frame)
            overlay.begin_frame()
            self.write(.2, self.rows)
            overlay.draw_detection_notice(0)
            report.assert_called_with(0, "2D view")
            self.assertEqual(self.rl.draw_text.call_args.args[0], "ROAD")


if __name__ == "__main__":
    unittest.main()
