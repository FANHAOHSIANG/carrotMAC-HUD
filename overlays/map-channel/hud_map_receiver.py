"""Latest-only map cache for the Mac renderer. No C4 filesystem paths."""
import io
import os
from pathlib import Path
import struct
import time

HEADER = struct.Struct('<4sQB')
MAX_BYTES = 32768


def preview(directory=None, now=None):
  if directory is None:
    from hud_runtime import DIRECTORY
    directory = DIRECTORY
    from hud_protocol import read_snapshot
    if read_snapshot() is None:
      return directory / 'nav-map.jpg', False
  now = time.time() if now is None else now
  target = directory / 'nav-map.jpg'
  try:
    with (directory / 'map.packet').open('rb') as source:
      packet = source.read(8 + MAX_BYTES + 1)
    if not 8 + HEADER.size <= len(packet) <= 8 + MAX_BYTES:
      return target, False
    received, = struct.unpack_from('<d', packet)
    if not 0 <= now - received < 2:
      return target, False
    magic, sequence, valid = HEADER.unpack_from(packet, 8)
    data = packet[8 + HEADER.size:]
    if magic != b'CM01' or valid != 1 or not data:
      return target, False
    # Reception stamp identifies each update, including after C4 restarts.
    marker = directory / 'nav-map.stamp'
    stamp = struct.pack('<dQ', received, sequence)
    if target.is_file() and marker.is_file() and marker.read_bytes() == stamp:
      return target, True
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
      if image.format != 'JPEG' or image.size != (256, 256):
        return target, False
      image.verify()
    temporary = target.with_suffix('.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, target)
    marker.write_bytes(stamp)
    return target, True
  except (OSError, ValueError, struct.error):
    return target, False
