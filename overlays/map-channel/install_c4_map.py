"""Install the map sender on a parked C4; preserve files on any failure."""
from datetime import datetime
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

FILES = ('tools/jetlink/hud_protocol.py', 'openpilot/selfdrive/modeld/jetlink/daemon.py', 'tools/jetlink/hud_map.py')


def main():
    root = Path('/data/openpilot')
    onroad = Path('/data/params/d/IsOnroad')
    if not onroad.exists() or onroad.read_bytes().strip() not in (b'0', b''):
        raise ValueError('請先熄火，保持 C4 供電，再安裝；無法確認 offroad 時會停止。')
    source = Path(__file__).resolve().parent
    patch = source / 'c4-map-channel.patch'
    check = subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], capture_output=True, text=True)
    if check.returncode:
        reverse = subprocess.run(['git', '-C', str(root), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
        if not reverse.returncode and (root / FILES[2]).exists() and (root / FILES[2]).read_bytes() == (source / 'hud_map.py').read_bytes():
            print('地圖通道已安裝。')
            return
        raise ValueError('目前 C4 原始碼與 carrot-nav 補丁不相容，未修改任何檔案：\n' + check.stderr)
    compile((source / 'hud_map.py').read_text(), 'hud_map.py', 'exec')
    backup = Path('/data/CarrotMacHUD-map-backups') / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    present = []
    for name in FILES:
        old = root / name
        if old.exists():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, saved)
            present.append(name)
    (backup / 'manifest.json').write_text(json.dumps(present))
    try:
        subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True)
        temporary = (root / FILES[2]).with_suffix('.update-tmp')
        shutil.copy2(source / 'hud_map.py', temporary)
        os.replace(temporary, root / FILES[2])
        for name in FILES:
            compile((root / name).read_text(), name, 'exec')
    except Exception:
        for name in FILES:
            if name in present:
                shutil.copy2(backup / name, root / name)
            else:
                (root / name).unlink(missing_ok=True)
        raise
    print(f'地圖發送端已安裝，備份：{backup}\n請保持停車並重新啟動 C4，再選 ClusterHudScreenMode=7。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
