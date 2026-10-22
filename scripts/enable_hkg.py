"""Install the hkg renderer adapter, preserving the existing Jetlink App."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

NAMES = ('hkg_hud.py', 'mac_hud_supervisor.py', 'hkg-hud.enabled')


def atomic_copy(source, target):
  tmp = target.with_name(target.name + '.hkg-tmp')
  shutil.copy2(source, tmp)
  os.replace(tmp, target)


def install(root, base):
  helper = base / 'carrot/tools/jetlink'
  for name in ('hud.py', 'hud_runtime.py', 'mac_hud_supervisor.py'):
    if not (helper / name).is_file():
      raise ValueError('需要先安裝可運作的 CarrotMacHUD（含 App 自動啟動）。缺少：' + name)
  revision = subprocess.check_output(['git', '-C', str(base / 'carrot'), 'rev-parse', 'HEAD'], text=True).strip()
  if revision != 'a564ce1dc082909b1fdc73b72e64d920336b34d6':
    raise ValueError('HUD renderer 版本不同，停止安裝；需要依實際版本適配。')
  runtime = (helper / 'hud_runtime.py').read_text()
  hud = (helper / 'hud.py').read_text()
  if 'PACKET' not in runtime or 'if not MAC:' not in hud or 'panel.lock' not in hud:
    raise ValueError('缺少 Mac HUD 適配／panel lock，保留現有安裝。')
  app = base / 'jetlink/macos/build/Jetlink.app/Contents/MacOS/Jetlink'
  if not app.is_file() or b'carrot_hud_v1' not in app.read_bytes():
    raise ValueError('現有 App 未找到 Carrot HUD receiver，保留 App；需先製作符合目前版本的 HUD App。')
  for source in (root / 'hkg/hkg_hud.py', root / 'AppAutostart/mac_hud_supervisor.py'):
    compile(source.read_text(), str(source), 'exec')
  backup = base / 'backups' / ('hkg-hud-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
  backup.mkdir(parents=True)
  existed = [name for name in NAMES if (helper / name).exists()]
  for name in existed:
    shutil.copy2(helper / name, backup / name)
  info = {'backup': str(backup), 'existed': existed, 'app_sha256': hashlib.sha256(app.read_bytes()).hexdigest()}
  try:
    atomic_copy(root / 'hkg/hkg_hud.py', helper / 'hkg_hud.py')
    atomic_copy(root / 'AppAutostart/mac_hud_supervisor.py', helper / 'mac_hud_supervisor.py')
    (helper / 'hkg-hud.enabled').touch()
    manifest = base / 'update/hkg-hud-backup.json'
    tmp = manifest.with_suffix('.tmp')
    tmp.write_text(json.dumps(info, indent=2))
    os.replace(tmp, manifest)
  except BaseException:
    restore_files(helper, backup, existed)
    raise
  print('hkg HUD adapter 已安裝；Jetlink App 未被替換。\n備份：' + str(backup))


def restore_files(helper, backup, existed):
  for name in NAMES:
    if name in existed:
      atomic_copy(backup / name, helper / name)
    else:
      (helper / name).unlink(missing_ok=True)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--base', type=Path, default=Path.home() / 'CarrotMacHUD')
  parser.add_argument('--rollback', action='store_true')
  args = parser.parse_args()
  if sys.platform != 'darwin':
    raise ValueError('請在 Mac 執行。')
  base = args.base.resolve()
  state = base / 'update'
  state.mkdir(parents=True, exist_ok=True)
  with (state / 'update.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.run(['pgrep', '-f', '(^|/)(Jetlink|mac_hud_supervisor.py|hkg_hud.py|hud.py)( |$)'],
                      stdout=subprocess.DEVNULL).returncode == 0:
      raise ValueError('請先退出 Jetlink App 並停止 HUD helper，再執行。')
    if args.rollback:
      manifest = state / 'hkg-hud-backup.json'
      info = json.loads(manifest.read_text())
      backup = Path(info['backup']).resolve()
      if not backup.is_relative_to((base / 'backups').resolve()):
        raise ValueError('無效備份路徑。')
      restore_files(base / 'carrot/tools/jetlink', backup, info['existed'])
      manifest.unlink()
      print('已還原 hkg HUD 安裝前的 helper。')
    else:
      if (state / 'hkg-hud-backup.json').exists():
        raise ValueError('已存在 hkg HUD 安裝紀錄；先 --rollback 後再更新，保留原始備份。')
      install(Path(__file__).resolve().parents[1], base)


if __name__ == '__main__':
  try:
    main()
  except (OSError, ValueError, subprocess.CalledProcessError) as exc:
    print('安裝停止：' + str(exc), file=sys.stderr)
    raise SystemExit(1)
