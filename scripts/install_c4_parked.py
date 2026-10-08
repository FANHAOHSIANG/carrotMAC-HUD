"""Install/restore the opt-in C4 patch while genuinely offroad, with backups."""
import argparse
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
BASE = 'e74e6938ddc4574b1ba19ee7405ff146f3c1728e'
FILES = [f'openpilot/selfdrive/modeld/jetlink/{name}.py' for name in ('daemon', 'mac', 'model', 'parked')]
PATCH = REPO / 'overlays/protocol3/c4-parked-model-switch.patch'


def run(*args, **kwargs):
  return subprocess.run([str(x) for x in args], check=True, **kwargs)


def offroad(params):
  if (params / 'IsOffroad').read_bytes() != b'1' or (params / 'IsOnroad').read_bytes() != b'0':
    raise ValueError('首次安裝／還原必須熄火，保持 C4 供電，等候 offroad 畫面。不可手動偽造 Params。')


def revision(root):
  return run('git', '-C', root, 'rev-parse', 'HEAD', capture_output=True, text=True).stdout.strip()


def restore(root, state, flag):
  record = json.loads((state / 'last-backup.json').read_text())
  backup = Path(record['backup']).resolve()
  if record['root'] != str(root.resolve()) or not backup.is_relative_to((state / 'backups').resolve()):
    raise ValueError('備份位置與 C4 source 不符。')
  if record['flag_existed']:
    raise ValueError('備份狀態不正確。')
  if not all((backup / name).is_file() for name in FILES[:-1]):
    raise ValueError('備份不完整，未覆蓋 C4 原始檔。')
  flag.unlink(missing_ok=True)
  for name in FILES:
    source, target = backup / name, root / name
    if source.is_file():
      pending = target.with_name(target.name + '.parked-restore')
      shutil.copy2(source, pending)
      os.replace(pending, target)
    elif name.endswith('/parked.py'):
      target.unlink(missing_ok=True)
    else:
      raise ValueError('備份缺少原始檔：' + name)


def install(root, state, flag, params, check_only=False):
  offroad(params)
  if revision(root) != BASE:
    raise ValueError('此實驗版僅驗證官方 carrot-wip ' + BASE + '。目前 C4 commit 不符；請勿強行套用。')
  changed = run('git', '-C', root, 'status', '--porcelain', '--', *FILES, capture_output=True, text=True).stdout
  if changed.strip():
    raise ValueError('待修補的 C4 檔案已有本機修改；保留現況並停止安裝。')
  if flag.exists():
    raise ValueError('已存在 parked-switch 啟用檔，請先查看先前安裝／還原狀態。')
  run('git', '-C', root, 'apply', '--check', PATCH)
  if check_only:
    print('官方基準與補丁檢查通過；尚未安裝或啟用。')
    return
  backup = state / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
  backup.mkdir(parents=True)
  for name in FILES:
    source = root / name
    if source.exists():
      target = backup / name
      target.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(source, target)
  record = dict(root=str(root.resolve()), backup=str(backup.resolve()), flag_existed=False, base=BASE)
  state.mkdir(parents=True, exist_ok=True)
  temporary = state / 'last-backup.tmp'
  temporary.write_text(json.dumps(record, indent=2) + '\n')
  os.replace(temporary, state / 'last-backup.json')
  try:
    offroad(params)
    run('git', '-C', root, 'apply', PATCH)
    for name in FILES:
      ast.parse((root / name).read_text(), filename=name)
    run(sys.executable, REPO / 'scripts/test_c4_parked.py', env=dict(os.environ, C4_SOURCE_ROOT=str(root)))
    offroad(params)
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text('1\n')
  except BaseException:
    restore(root, state, flag)
    raise
  print('修補與 CPU 測試完成。請保持熄火並重啟 C4；仍需停車實機驗證。\n備份：' + str(backup))


def main():
  parser = argparse.ArgumentParser()
  action = parser.add_mutually_exclusive_group(required=True)
  action.add_argument('--check', action='store_true')
  action.add_argument('--install', action='store_true')
  action.add_argument('--rollback', action='store_true')
  parser.add_argument('--root', type=Path, default=Path('/data/openpilot'))
  args = parser.parse_args()
  state, flag, params = Path('/data/carrot-parked-switch-state'), Path('/data/jetlink-parked-model-switch'), Path('/data/params/d')
  offroad(params)
  root = args.root.resolve()
  with (state.parent / 'carrot-parked-switch.lock').open('a') as lock:
    import fcntl
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.rollback:
      if revision(root) != BASE:
        flag.unlink(missing_ok=True)
        raise ValueError('已停用 parked-switch，但 C4 已更新到其他 commit；不覆蓋成舊版。請重啟並保留備份。')
      restore(root, state, flag)
      print('已還原原始檔。請保持熄火並重啟 C4。')
    else:
      install(root, state, flag, params, check_only=args.check)


if __name__ == '__main__':
  try:
    main()
  except (ValueError, OSError, subprocess.CalledProcessError) as error:
    print('C4 修補停止：' + str(error), file=sys.stderr)
    sys.exit(1)
