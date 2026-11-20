import base64
import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from vision import packet_frame, publish_results, smooth


class PacketClockTest(unittest.TestCase):
    def test_shared_capture_epoch(self):
        wall = 1794999000.
        msg = {"sent": 42., "cameras": {"road": {"frame": 7, "time": 41.99, "capture_time": 41.9,
                                                 "jpeg": base64.b64encode(b"image").decode()}}}
        def read(receipt_age):
            payload = struct.pack("<d", wall-receipt_age) + json.dumps(msg).encode()
            return packet_frame(payload, wall)

        key, stamp, jpeg = read(.125)
        self.assertEqual((key[0], jpeg), (7, b"image"))
        self.assertAlmostEqual(stamp, wall-.225, places=5)
        self.assertIsNone(read(.5))
        self.assertIsNone(read(-1.))
        msg["cameras"]["road"]["capture_time"] = 40.
        self.assertIsNone(read(0.))

    def test_hd_and_displayed_road_share_source_identity(self):
        frame = {"frame": 639, "time": 32.02, "capture_time": 32., "jpeg": "bG93"}
        cameras = {"road": frame, "road_hd": dict(frame, jpeg="aGlnaA=="),
                   "wide": dict(frame, jpeg="d2lkZQ==")}

        def read():
            body = json.dumps({"sent": 32.1, "cameras": cameras}).encode()
            return packet_frame(struct.pack("<d", 500.) + body, 500.03)

        key, stamp, jpeg = read()
        self.assertEqual((key, jpeg), ((639, 32., "capture"), b"high"))
        self.assertAlmostEqual(stamp, 499.9)
        cameras["road_hd"]["frame"] += 1
        self.assertEqual((read()[0], read()[2]), ((639, 32., "capture"), b"low"))
        cameras["road_hd"]["frame"] = 639
        cameras["road_hd"]["capture_time"] += .05
        self.assertEqual(read()[2], b"low")
        del cameras["road"]["capture_time"]
        self.assertEqual(read()[0], (639, 32.02, "preview"))
        del cameras["road"], cameras["road_hd"]
        self.assertIsNone(read())  # no narrow image even if a WIDE frame has the same id

    def test_independent_current_frame_and_legacy_scene_results(self):
        raw = [["car", .55, .70, .18, .13]]
        scene = smooth([["car", .50, .69, .18, .13]], [row.copy() for row in raw])
        with TemporaryDirectory() as dirname:
            cache = Path(dirname)
            publish_results(cache, (12, 174.5, "capture"), 300., scene, raw)
            legacy_stamp, legacy_boxes = json.loads((cache / "vision.json").read_text())
            self.assertEqual(legacy_stamp, 300.)
            self.assertAlmostEqual(legacy_boxes[0][1], .535)
            self.assertEqual(json.loads((cache / "vision-frame.json").read_text()),
                             {"version": 2, "camera": "road", "frame_id": 12,
                              "source_time": 174.5, "time_kind": "capture",
                              "stamp": 300., "objects": [["car", .55, .70, .18, .13]]})
            publish_results(cache, (13, 174.55, "capture"), 300.05, [], [])
            self.assertEqual(json.loads((cache / "vision-frame.json").read_text())["objects"], [])
            self.assertEqual(json.loads((cache / "vision.json").read_text())[1], [])
            self.assertEqual(list(cache.glob("*.tmp")), [])
