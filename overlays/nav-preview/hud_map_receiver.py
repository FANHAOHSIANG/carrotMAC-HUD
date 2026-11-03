"""Read mapsd's bounded PNG from the existing Mac HUD snapshot channel."""
import base64
import hashlib
import io
import math
import os
from pathlib import Path
import struct
import time

MAX_BYTES = 32 * 1024
MAX_AGE = 2.


class NavPreview:
    def __init__(self, read_snapshot, directory):
        self.read_snapshot = read_snapshot
        self.path = Path(directory) / 'nav-map.png'
        self.digest = None

    def preview(self):
        try:
            snapshot = self.read_snapshot()
            if snapshot is None:
                return self.path, False
            received, record = snapshot
            if record.get('params', {}).get('ClusterHudScreenMode') != 'Nw==':
                return self.path, False
            value = record['nav_map_preview']
            elapsed = time.monotonic() - received
            source_age = float(value['age'])
            age = source_age + elapsed
            if not (math.isfinite(age) and 0 <= elapsed < .5 and 0 <= source_age and age < MAX_AGE):
                return self.path, False
            encoded = value['png']
            if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
                return self.path, False
            data = base64.b64decode(encoded, validate=True)
            if not (24 <= len(data) <= MAX_BYTES and
                    data[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' and
                    struct.unpack('>II', data[16:24]) == (256, 256)):
                return self.path, False
            digest = hashlib.sha256(data).hexdigest()
            if digest != value['sha256']:
                return self.path, False
            if digest != self.digest or not self.path.is_file():
                from PIL import Image
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != 'PNG' or image.size != (256, 256):
                        return self.path, False
                    image.load()
                # macOS has no /dev/shm. Stay in the existing private HUD cache.
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.png.tmp')
                temporary.write_bytes(data)
                os.replace(temporary, self.path)
                self.digest = digest
            return self.path, True
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, struct.error):
            return self.path, False


_receiver = None


def preview():
    global _receiver
    if _receiver is None:
        from hud_runtime import DIRECTORY
        from hud_protocol import read_snapshot
        # read_snapshot already translates Swift's epoch stamp to Python's
        # local monotonic clock. Never compare the C4 clock to the Mac clock.
        _receiver = NavPreview(read_snapshot, DIRECTORY)
    return _receiver.preview()
