import base64
import json
import struct
import unittest

from vision import packet_frame


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
