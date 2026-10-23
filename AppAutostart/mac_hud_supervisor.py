"""App-owned HUD child with bounded restart and process-group cleanup."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import struct
import sys
import time


def packet_kind(path, now=None):
  """Identify the display protocol, never a branch name or a stale cached file."""
  try:
    with path.open('rb') as stream:
      raw = stream.read(96 * 1024 + 9)
    if not 8 < len(raw) <= 96 * 1024 + 8:
      return None
    received, = struct.unpack_from('<d', raw)
    age = (time.time() if now is None else now) - received
    if not 0 <= age < .5:
      return None
    value = json.loads(raw[8:])
    if not isinstance(value, dict) or value.get('version') != 1:
      return None
    if not math.isfinite(float(value['sent'])):
      return None
    if not all(isinstance(value.get(k), dict) for k in ('events', 'params', 'valid', 'alive', 'received', 'mono')):
      return None
    if value.get('source') == 'hkg_hud_v1':
      if len(raw) <= 14 * 1024 + 8 and all(isinstance(value.get(k), dict) for k in ('hkg', 'age')):
        return 'hkg', received
    elif value.get('source') in (None, 'carrot_hud_v1') and 'hkg' not in value:
      return 'carrot', received
  except (OSError, ValueError, TypeError, KeyError, struct.error, OverflowError):
    pass
  return None


class AutoCommand:
  """Require two distinct fresh packets; absence never changes the active HUD."""
  def __init__(self, here, packet):
    self.here, self.packet = here, packet
    self.current = self.candidate = self.stamp = None

  def __call__(self):
    observed = packet_kind(self.packet)
    if observed is None:
      self.candidate = self.stamp = None
    else:
      kind, stamp = observed
      if kind == self.current:
        self.candidate = self.stamp = None
      elif kind != self.candidate:
        self.candidate, self.stamp = kind, stamp
      elif stamp > self.stamp:
        self.current = kind
        self.candidate = self.stamp = None
        print('HUD auto-detected: ' + ('HKG' if kind == 'hkg' else 'Carrotpilot'), flush=True)
    if self.current is None:
      return None
    helper = 'hkg_hud.py' if self.current == 'hkg' else 'hud.py'
    return [sys.executable, '-u', str(self.here / helper)]


def terminate_group(child, grace=2.):
  # ffmpeg and decoder children inherit this group. A helper that already
  # exited can still leave descendants, so kill the group regardless of poll.
  try:
    os.killpg(child.pid, signal.SIGTERM)
  except ProcessLookupError:
    pass
  deadline = time.monotonic() + grace
  while time.monotonic() < deadline:
    try:
      os.killpg(child.pid, 0)
    except ProcessLookupError:
      break
    child.poll()  # reap the leader while waiting for encoder workers
    time.sleep(.05)
  try:
    os.killpg(child.pid, signal.SIGKILL)
  except ProcessLookupError:
    pass
  child.wait(timeout=1.)


def supervise(command, parent_pid, directory, retry=2., select_command=None):
  directory.mkdir(mode=0o700, parents=True, exist_ok=True)
  stopped = False
  def stop(signum, frame):
    nonlocal stopped
    stopped = True
  old_handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
  lock = (directory / 'supervisor.lock').open('a')
  child = None
  try:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      print('Carrot HUD supervisor already running; leaving it alone.', flush=True)
      return 75
    while not stopped and os.getppid() == parent_pid:
      if select_command is not None:
        command = select_command()
        if command is None:
          time.sleep(.1)
          continue
      print('Starting HUD helper: ' + Path(command[-1]).name, flush=True)
      child = subprocess.Popen(command, start_new_session=True)
      switching = False
      while child.poll() is None and not stopped and os.getppid() == parent_pid:
        if select_command is not None:
          selected = select_command()
          if selected is not None and selected != command:
            switching = True
            break
        time.sleep(.1)
      code = child.poll()
      terminate_group(child)
      child = None
      (directory / 'status.json').unlink(missing_ok=True)
      if stopped or os.getppid() != parent_pid:
        break
      if switching:
        # Cleanup above releases the USB panel and kills encoder descendants
        # before the other renderer starts. Never run two panel owners.
        print('HUD source changed; previous renderer stopped.', flush=True)
        continue
      # Normal ignition-off/window close also needs a new waiting helper.
      print(f'Carrot HUD exited ({code}); waiting {retry:g}s before restart', flush=True)
      deadline = time.monotonic() + retry
      while not stopped and os.getppid() == parent_pid and time.monotonic() < deadline:
        time.sleep(.1)
    return 0
  finally:
    if child is not None:
      terminate_group(child)
    lock.close()
    for sig, handler in old_handlers.items():
      signal.signal(sig, handler)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--parent-pid', required=True, type=int)
  args = parser.parse_args()
  from hud_runtime import DIRECTORY
  root = Path(__file__).resolve().parents[2]
  env = os.environ
  env['PYTHONPATH'] = str(root) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
  env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + env.get('PATH', '')
  env['PYTHONUNBUFFERED'] = '1'
  here = Path(__file__).resolve().parent
  command = [sys.executable, '-u', str(here / 'hud.py')]
  auto = AutoCommand(here, DIRECTORY / 'snapshot.packet') if (here / 'hkg_hud.py').is_file() else None
  if auto is not None:
    print('HUD automatic mode: waiting for fresh HKG / Carrotpilot packets.', flush=True)
  return supervise(command, args.parent_pid, DIRECTORY, select_command=auto)


if __name__ == '__main__':
  raise SystemExit(main())

