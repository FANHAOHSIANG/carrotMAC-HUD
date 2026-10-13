import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('receiver', ROOT / 'overlays/map-channel/hud_map_receiver.py')
receiver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receiver)


spec = importlib.util.spec_from_file_location('sender', ROOT / 'overlays/map-channel/hud_map.py')
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


class MapChannelTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        output = io.BytesIO()
        Image.new('RGB', (256, 256), (12, 34, 56)).save(output, 'JPEG')
        self.jpeg = output.getvalue()

    def tearDown(self):
        self.temp.cleanup()

    def packet(self, data=None, *, stamp=100., valid=1, magic=b'CM01'):
        data = self.jpeg if data is None else data
        (self.root / 'map.packet').write_bytes(struct.pack('<d4sQB', stamp, magic, 1, valid) + data)

    def test_map_id_keeps_existing_wifi_and_startup_ids_free(self):
        self.assertEqual(sender.MESSAGE, 0x4004)
        self.assertNotIn(sender.MESSAGE, (0x4000, 0x4001, 0x4002, 0x4003))

    def test_sender_to_mac_roundtrip_and_invalid_route_clear(self):
        from PIL import Image
        source = self.root / 'map.png'
        Image.new('RGB', (256, 256), (12, 34, 56)).save(source)
        import os
        os.utime(source, (100., 100.))
        encoded = sender.encode_preview(source, ready=True, sequence=1, now=100.1)
        self.assertLessEqual(len(encoded), 32768)
        (self.root / 'map.packet').write_bytes(struct.pack('<d', 100.) + encoded)
        self.assertTrue(receiver.preview(self.root, now=100.1)[1])
        cleared = sender.encode_preview(source, ready=False, sequence=2, now=100.1)
        (self.root / 'map.packet').write_bytes(struct.pack('<d', 100.) + cleared)
        self.assertFalse(receiver.preview(self.root, now=100.1)[1])
        stale = sender.encode_preview(source, ready=True, sequence=3, now=102.)
        self.assertEqual(sender.HEADER.unpack(stale)[2], 0)

    def test_sender_rejects_duplicate_stale_and_oversize_ipc(self):
        source = self.root / 'ipc.packet'
        wire = sender.HEADER.pack(b'CM01', 1, 0)
        source.write_bytes(sender.STAMP.pack(100.) + wire)
        stamp, value = sender.read_latest(source, 0., now=100.1)
        self.assertEqual(value, wire)
        self.assertIsNone(sender.read_latest(source, stamp, now=100.1)[1])
        self.assertIsNone(sender.read_latest(source, 0., now=101.)[1])
        source.write_bytes(sender.STAMP.pack(100.) + b'x' * 32769)
        self.assertIsNone(sender.read_latest(source, 0., now=100.1)[1])

    def test_valid_frame_reaches_cache_and_expires(self):
        self.packet()
        path, fresh = receiver.preview(self.root, now=100.1)
        self.assertTrue(fresh)
        self.assertEqual(path.read_bytes(), self.jpeg)
        self.assertFalse(receiver.preview(self.root, now=102.)[1])
        self.assertFalse(receiver.preview(self.root, now=99.)[1])

    def test_clear_does_not_reuse_previous_texture(self):
        self.packet()
        self.assertTrue(receiver.preview(self.root, now=100.1)[1])
        self.packet(b'', valid=0, stamp=100.2)
        self.assertFalse(receiver.preview(self.root, now=100.3)[1])

    def test_bad_header_jpeg_and_oversize_are_rejected(self):
        for data, magic in [(b'garbage', b'CM01'), (self.jpeg, b'BAD!'), (b'x' * 32769, b'CM01')]:
            self.packet(data, magic=magic)
            self.assertFalse(receiver.preview(self.root, now=100.1)[1])

    def test_wrong_image_size_rejected(self):
        from PIL import Image
        output = io.BytesIO()
        Image.new('RGB', (512, 512)).save(output, 'JPEG')
        self.packet(output.getvalue())
        self.assertFalse(receiver.preview(self.root, now=100.1)[1])

    def test_new_receive_stamp_replaces_cache_after_sequence_restart(self):
        self.packet()
        self.assertTrue(receiver.preview(self.root, now=100.1)[1])
        self.packet(stamp=101.)
        self.assertTrue(receiver.preview(self.root, now=101.1)[1])
        self.assertEqual((self.root / 'nav-map.stamp').read_bytes(), struct.pack('<dQ', 101., 1))


if __name__ == '__main__':
    unittest.main()
