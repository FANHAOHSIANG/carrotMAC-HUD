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

NAMES = ('hkg_hud.py', 'hkg_display.py', 'mac_hud_supervisor.py', 'hkg-hud.enabled')


def atomic_copy(source, target):
  tmp = target.with_name(target.name + '.hkg-tmp')
  shutil.copy2(source, tmp)
  os.replace(tmp, target)


def check_app(data):
  """Static installation preflight, not proof of a successful USB handshake.

  The installed 0.8.7 HUD build has the receiver class/writer and supervisor
  markers but no contiguous carrot_hud_v1 bytes. Check the receiver's own
  implementation markers as an alternative, never the class name alone.
  """
  if b'carrot_hud_v1' in data:
    evidence = 'capability marker'
  elif b'CarrotHUD' in data and b'carrot-hud-writer' in data:
    evidence = 'receiver class + writer thread'
  else:
    raise ValueError('無法確認現有 App 的 Carrot HUD receiver，保留 App；請提供 App 版本與檢查結果。')
  if b'mac_hud_supervisor.py' not in data:
    raise ValueError('無法確認現有 App 的 HUD helper 自動啟動功能，保留 App。')
  return evidence


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
  if not app.is_file():
    raise ValueError('找不到既有 Jetlink App：' + str(app))
  app_data = app.read_bytes()
  evidence = check_app(app_data)
  for source in (root / 'hkg/hkg_hud.py', root / 'hkg/hkg_display.py', root / 'AppAutostart/mac_hud_supervisor.py'):
    compile(source.read_text(), str(source), 'exec')
  manifest = base / 'update/hkg-hud-backup.json'
  previous = json.loads(manifest.read_text()) if manifest.exists() else None
  if previous is not None:
    original = Path(previous['backup']).resolve()
    if not original.is_relative_to((base / 'backups').resolve()) or not original.is_dir():
      raise ValueError('原始備份不存在或路徑無效，停止更新。')
  backup = base / 'backups' / ('hkg-hud-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
  backup.mkdir(parents=True)
  existed = [name for name in NAMES if (helper / name).exists()]
  for name in existed:
    shutil.copy2(helper / name, backup / name)
  info = {'backup': str(backup), 'existed': existed, 'app_sha256': hashlib.sha256(app_data).hexdigest(),
          'app_hud_evidence': evidence}
  if previous is not None:
    # Retain the first pre-HKG backup for --rollback. The update backup lets
    # a failed copy restore the working adapter instead of disabling it.
    info = {**previous, 'last_update_backup': str(backup), 'app_hud_evidence': evidence}
  try:
    atomic_copy(root / 'hkg/hkg_hud.py', helper / 'hkg_hud.py')
    atomic_copy(root / 'hkg/hkg_display.py', helper / 'hkg_display.py')
    atomic_copy(root / 'AppAutostart/mac_hud_supervisor.py', helper / 'mac_hud_supervisor.py')
    (helper / 'hkg-hud.enabled').touch()
    tmp = manifest.with_suffix('.tmp')
    tmp.write_text(json.dumps(info, indent=2))
    os.replace(tmp, manifest)
  except BaseException:
    restore_files(helper, backup, existed)
    raise
  print('hkg HUD adapter 已安裝；Jetlink App 未被替換。\n備份：' + str(backup))
  print('App 靜態檢查：' + evidence + '；實際接收仍需連接 C4 確認。')


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
      install(Path(__file__).resolve().parents[1], base)


if __name__ == '__main__':
  try:
    main()
  except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
    print('安裝停止：' + str(exc), file=sys.stderr)
    raise SystemExit(1)
