"""Negotiated, bounded mode-7 map preview; encoding stays out of inference."""
import io
import os
from pathlib import Path
import signal
import struct
import sys
import time

CAPABILITY = 'carrot_map_v1'
MESSAGE = 0x4002
HEADER = struct.Struct('<4sQB')
STAMP = struct.Struct('<d')
MAX_BYTES = 32 * 1024


def encode_preview(path, *, ready, sequence, now=None):
  now = time.time() if now is None else now
  empty = HEADER.pack(b'CM01', sequence, 0)
  try:
    if not ready or not 0 <= now - path.stat().st_mtime < 2:
      return empty
    from PIL import Image
    with Image.open(path) as image:
      if image.size != (256, 256):
        return empty
      image = image.convert('RGB')
      for quality in (80, 65, 45):
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=quality)
        data = HEADER.pack(b'CM01', sequence, 1) + output.getvalue()
        if len(data) <= MAX_BYTES:
          return data
  except (OSError, ValueError):
    pass
  return empty


def read_latest(path, previous, now=None):
  now = time.monotonic() if now is None else now
  try:
    with path.open('rb') as source:
      data = source.read(STAMP.size + MAX_BYTES + 1)
    if not STAMP.size + HEADER.size <= len(data) <= STAMP.size + MAX_BYTES:
      return previous, None
    stamp, = STAMP.unpack_from(data)
    if stamp == previous or not 0 <= now - stamp < .75:
      return previous, None
    return stamp, data[STAMP.size:]
  except (OSError, struct.error):
    return previous, None


def main(path):
  import ctypes
  from openpilot.common.params import Params
  from openpilot.common.display_scheduling import DisplayScheduler
  from openpilot.selfdrive.navigation.preview import PREVIEW_PATH, preview_reason
  ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0)
  if os.getppid() == 1:
    return
  def stop(*_):
    raise SystemExit
  signal.signal(signal.SIGTERM, stop)
  params = Params()
  scheduler = DisplayScheduler(7, enabled=True)
  sequence = 0
  try:
    while True:
      started = time.monotonic()
      scheduler.update(params.get_bool('IsOnroad'))
      sequence += 1
      ready = params.get_int('ClusterHudScreenMode') == 7 and preview_reason() == 'ready'
      data = encode_preview(PREVIEW_PATH, ready=ready, sequence=sequence)
      temporary = path.with_suffix('.tmp')
      temporary.write_bytes(STAMP.pack(time.monotonic()) + data)
      os.replace(temporary, path)
      time.sleep(max(0, started + .5 - time.monotonic()))
  finally:
    path.unlink(missing_ok=True)
    path.with_suffix('.tmp').unlink(missing_ok=True)


if __name__ == '__main__':
  main(Path(sys.argv[1]))
