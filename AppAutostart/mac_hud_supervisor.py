"""App-owned HUD child with bounded restart and process-group cleanup."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


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


def supervise(command, parent_pid, directory, retry=2.):
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
      print('Starting Carrot HUD helper', flush=True)
      child = subprocess.Popen(command, start_new_session=True)
      while child.poll() is None and not stopped and os.getppid() == parent_pid:
        time.sleep(.1)
      code = child.poll()
      terminate_group(child)
      child = None
      (directory / 'status.json').unlink(missing_ok=True)
      if stopped or os.getppid() != parent_pid:
        break
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
  return supervise([sys.executable, '-u', str(Path(__file__).with_name('hud.py'))], args.parent_pid, DIRECTORY)


if __name__ == '__main__':
  raise SystemExit(main())
