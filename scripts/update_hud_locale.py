"""Install the display patches on the pinned Mac HUD renderer."""

import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

from mac_install import revision, run


def apply_hud_patches(carrot, patches, rollback):
    command = ('git', '-C', carrot, 'apply')
    direction = ('--reverse',) if rollback else ()
    opposite = () if rollback else ('--reverse',)
    pending = [
        patch for patch in patches
        if subprocess.run([*command, *opposite, '--check', patch], capture_output=True).returncode
    ]
    if not pending:
        return False
    run(*command, *direction, '--check', *pending)
    run(*command, *direction, *pending)
    return True


def main():
    parser = argparse.ArgumentParser(description='更新或還原 Mac HUD 繁中與 P／R 檔畫面')
    parser.add_argument('--rollback', action='store_true', help='還原 Mac HUD 畫面更新')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise ValueError('請在 Mac 執行。')

    root = Path(__file__).resolve().parents[1]
    base = Path.home() / 'CarrotMacHUD'
    carrot = base / 'carrot'
    versions = json.loads((root / 'versions.json').read_text())
    if revision(carrot) != versions['carrot_revision']:
        raise ValueError('Mac HUD 原始碼版本不相符。')
    if not (carrot / 'tools/jetlink/hud_runtime.py').is_file():
        raise ValueError('找不到已安裝的 Mac HUD helper。')
    overlays = root / 'overlays/protocol3'
    patches = (overlays / 'carrot-hud-zh-tw.patch', overlays / 'carrot-hud-gear.patch')
    state = base / 'update'
    state.mkdir(exist_ok=True)
    runtime = Path(os.environ.get(
        'CARROT_HUD_DIR', str(Path.home() / 'Library/Caches/io.zoompilot.jetlink/carrot-hud'),
    ))
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)

    with ExitStack() as locks:
        for path in (state / 'update.lock', runtime / 'supervisor.lock', runtime / 'panel.lock'):
            handle = locks.enter_context(path.open('a'))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('請先退出 Jetlink 和 HUD helper，並等候其他更新結束。') from exc
        process = subprocess.run(['pgrep', '-x', 'Jetlink'], stdout=subprocess.DEVNULL)
        if process.returncode == 0:
            raise ValueError('請先退出 Jetlink App。')
        if process.returncode != 1:
            process.check_returncode()
        changed = apply_hud_patches(carrot, patches, args.rollback)

    if args.rollback:
        print('Mac HUD 畫面更新已還原。' if changed else 'Mac HUD 已是還原狀態。')
    else:
        print('Mac HUD 繁中與 P／R 檔畫面更新完成。' if changed else 'Mac HUD 已是最新畫面版本。')
        print('重新開啟原本的 Jetlink App，HUD 會跟隨 C4 的語言設定。')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f'Mac HUD 更新停止：{error}')
