"""Experimental offline-only Mac Metal VLA replay. No Jetlink or vehicle interface.
Derived from TonyBinheWu/sunnypilot b0ba1f13db3fbed94ea88c8b93cec488ef3c2b7f; see LICENSE.upstream.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request

QUESTIONS = {
  'longitudinal': 'stop, yield, follow, search (for a gap), pass, adapt (speed to road conditions), track (maintain set speed)',
  'lateral': 'turn, change (lanes), merge, out (nudge out of lane), in (nudge within lane), park (pull over), abort, keep (stay centered)',
  'direction': 'left, right, straight',
}
SYSTEM = 'Predict the driving action from the forward camera and observed past ego motion. Answer with the appropriate English verb or direction.'


def prompts(history):
  if not isinstance(history, list) or len(history) != 9:
    raise ValueError('Expected nine observed poses sampled at 0.25 s ending at the image time')
  for pose in history:
    if not isinstance(pose, list) or len(pose) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in pose):
      raise ValueError('Invalid observed x/y/yaw')
  if any(abs(v) > 1e-4 for v in history[-1]):
    raise ValueError('Pose history must be in the current vehicle frame')
  trajectory = '\n'.join(f'<wp>[{x:.2f},{y:.2f},{yaw:.4f}]</wp>' for x, y, yaw in history)
  before = f'<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n'
  after = []
  for axis, choices in QUESTIONS.items():
    after.append('\n[PAST-VEHICLE-MOTION]:\n' + trajectory + f'\nSelect {axis} from: {choices}.'
                 + '<|im_end|>\n<|im_start|>assistant\n{"' + axis + '":"')
  return before, after


MODEL = 'PhysicalAI-reason-VLA.Q4_K_M.gguf'
PROJECTOR = 'PhysicalAI-reason-VLA.mmproj-Q8_0.gguf'
REVISION = '841fac174b8e3da0d5ca7ee56a2b15c879b1fb29'
ARTIFACTS = {
  MODEL: (2496755488, 'ac65d271619784787fab81d31685bc4b62e46a755c07710f9a456f7af5c73968'),
  PROJECTOR: (453974240, '2cf0f9a143c8f85851bbc768086c02ee433d41cf817a91f65d6c2dfb2d1e4edc'),
}


def verify(directory):
  for name, (size, digest) in ARTIFACTS.items():
    path = directory / name
    if path.stat().st_size != size:
      raise ValueError(f'Incorrect size for {name}')
    with path.open('rb') as f:
      if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
        raise ValueError(f'Incorrect checksum for {name}')


def resize_road(rgb):
  import cv2
  height, width = rgb.shape[:2]
  scaled_height = max(32, round(320 * height / width / 32) * 32)
  if not 128 <= scaled_height <= 256:
    raise ValueError('Expected a landscape forward camera')
  return cv2.resize(rgb, (320, scaled_height), interpolation=cv2.INTER_AREA)


def samples(manifest):
  import cv2
  import numpy as np
  with manifest.open(encoding='utf-8-sig') as f:
    for line in f:
      row = json.loads(line)
      timestamp = row['timestamp_us']
      if type(timestamp) is not int or timestamp < 0:
        raise ValueError('Expected recorded camera timestamp_us')
      prompts(row['egomotion'])
      path = (manifest.parent / row['image']).resolve()
      if not path.is_relative_to(manifest.parent.resolve()) or path.stat().st_size > 8 << 20:
        raise ValueError('Invalid frame path or file size')
      bgr = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
      if bgr is None or min(bgr.shape[:2]) < 32:
        raise ValueError(f'Invalid image {path.name}')
      yield row, resize_road(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def decode(words):
  if len(words) != 3:
    raise ValueError('Expected longitudinal, lateral and direction outputs')
  longitudinal, maneuver, direction = words
  speed = {'stop': 'stop', 'yield': 'yield', 'follow': 'follow', 'search': 'gap search', 'pass': 'pass',
           'adapt': 'adapt speed', 'track': 'cruise'}.get(longitudinal)
  lateral = {'keep': 'keep lane', 'merge': 'merge', 'park': 'pull over', 'abort': 'abort maneuver'}.get(maneuver)
  sided = {'turn': 'turn', 'change': 'lane change', 'out': 'nudge out', 'in': 'nudge in'}
  if maneuver in sided and direction in ('left', 'right'):
    lateral = f'{sided[maneuver]} {direction}'
  return {'longitudinal': speed, 'lateral': lateral}


def select_metal(listing, requested=None):
  """Select only a device explicitly listed as Metal; never silently select CPU."""
  found = {}
  for line in listing.splitlines():
    match = re.match(r'^\s*(MTL\d+|Metal\d*):\s*(.+)$', line, re.I)
    if match:
      found[match.group(1)] = match.group(2).strip()
  if requested is None and len(found) == 1:
    requested = next(iter(found))
  if requested not in found:
    raise ValueError('Expected an explicit available Metal device: ' + ', '.join(found))
  return requested, found[requested]

def fetch_weights(directory):
  directory.mkdir(parents=True, exist_ok=True)
  base = f'https://huggingface.co/mradermacher/PhysicalAI-reason-VLA-GGUF/resolve/{REVISION}'
  for name, (size, digest) in ARTIFACTS.items():
    destination = directory / name
    if destination.exists():
      with destination.open('rb') as f:
        if destination.stat().st_size == size and hashlib.file_digest(f, 'sha256').hexdigest() == digest:
          continue
      raise ValueError(f'Existing file failed verification: {destination}; move it aside first')
    fd, tmp = tempfile.mkstemp(prefix=name + '.', suffix='.part', dir=directory)
    try:
      h = hashlib.sha256()
      count = 0
      with os.fdopen(fd, 'wb') as f, urllib.request.urlopen(base + '/' + name, timeout=60) as response:
        while chunk := response.read(1024 * 1024):
          count += len(chunk)
          if count > size:
            raise ValueError('Unexpected download size')
          h.update(chunk)
          f.write(chunk)
      if count != size or h.hexdigest() != digest:
        raise ValueError('Weight verification failed')
      os.replace(tmp, destination)
    finally:
      Path(tmp).unlink(missing_ok=True)
  verify(directory)

@contextmanager
def reference(directory, server, gpu):
  import cv2
  devices = subprocess.check_output([server, '--list-devices'], stderr=subprocess.STDOUT, text=True, timeout=20)
  gpu, description = select_metal(devices, gpu)
  with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
  key = secrets.token_hex(32)
  opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

  def request(path, body=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/{path}', data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'})
    with opener.open(req, timeout=60) as response:
      return json.load(response)

  cmd = [server, '--host', '127.0.0.1', '--port', str(port), '--api-key', key, '--offline', '-m', directory/MODEL,
         '--mmproj', directory/PROJECTOR, '--device', gpu, '--mmproj-device', gpu, '-ngl', '99', '--fit', 'off', '-np', '1',
         '--ctx-size', '2048', '--image-min-tokens', '4', '--image-max-tokens', '1024']
  with tempfile.TemporaryFile() as log:
    proc = subprocess.Popen(cmd, stdout=log, stderr=log)
    try:
      until = time.monotonic() + 90
      while proc.poll() is None:
        try:
          if request('health').get('status') == 'ok':
            break
        except (OSError, ValueError):
          pass
        if time.monotonic() >= until:
          raise TimeoutError('VLA server startup timed out')
        time.sleep(.2)
      else:
        log.seek(0)
        raise RuntimeError(log.read()[-2000:].decode(errors='replace').replace(key, '[redacted]'))
      props = request('props')
      if not props['modalities']['vision'] or not props['build_info'].startswith('b12676-'):
        raise ValueError('Expected multimodal llama.cpp build b12676')
      marker = props['media_marker']

      def predict(rgb, history):
        ok, png = cv2.imencode('.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if not ok:
          raise ValueError('Could not encode frame')
        image = base64.b64encode(png).decode('ascii')
        before, tails = prompts(history)
        return [request('completion', {'prompt': {'prompt_string': before+marker+tail, 'multimodal_data': [image]},
                                       'n_predict': 1, 'temperature': 0, 'cache_prompt': False})['content'] for tail in tails]
      yield gpu + ': ' + description, predict
    finally:
      proc.terminate()
      try:
        proc.wait(timeout=10)
      except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def require_jetlink_stopped():
  result = subprocess.run(['/usr/bin/pgrep', '-x', 'Jetlink'], stdout=subprocess.DEVNULL)
  if result.returncode != 1:
    raise RuntimeError('Quit Jetlink before offline VLA replay; disconnect comma and stop HUD as well')

def main():
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument('--weights', type=Path, required=True)
  p.add_argument('--fetch', action='store_true')
  p.add_argument('--manifest', type=Path, required=True, help='Recorded local JSONL; no live inputs')
  p.add_argument('--server', type=Path, required=True, help='Pinned b12676 llama-server binary')
  p.add_argument('--device', help='Metal device identifier from --list-devices')
  p.add_argument('--max-frames', type=int, default=13)
  p.add_argument('--offline-bench', action='store_true', required=True, help='Confirm parked/offline, Jetlink and HUD stopped, comma disconnected')
  a = p.parse_args()
  if platform.system() != 'Darwin' or platform.machine() != 'arm64':
    p.error('Apple silicon macOS required')
  require_jetlink_stopped()
  if a.max_frames < 1:
    p.error('--max-frames must be positive')
  if not a.manifest.is_file():
    p.error('Recorded manifest required')
  if not a.server.is_file() or not os.access(a.server, os.X_OK):
    p.error('Executable llama-server required')
  if a.fetch:
    fetch_weights(a.weights)
  else:
    verify(a.weights)
  from itertools import islice
  count = 0
  with reference(a.weights.resolve(), a.server.resolve(), a.device) as (device, predict):
    for row, rgb in islice(samples(a.manifest.resolve()), a.max_frames):
      require_jetlink_stopped()
      started = time.perf_counter()
      words = predict(rgb, row['egomotion'])
      elapsed = (time.perf_counter() - started) * 1000
      result = {'image': row['image'], 'timestamp_us': row['timestamp_us'],
                'backend': 'metal', 'device': device, 'vla': 'mjf-su/PhysicalAI-reason-VLA',
                'weights_revision': REVISION, 'action': decode(words),
                'inference_ms': round(elapsed, 2)}
      result['camera_source'] = row.get('camera_source', 'unspecified')
      result['camera_quality'] = row.get('camera_quality', 'unspecified')
      if 'primary' in row:
        result['primary'] = row['primary']
      print(json.dumps(result, ensure_ascii=False), flush=True)
      count += 1
  if not count:
    raise ValueError('No valid recorded samples')

if __name__ == '__main__':
  main()
