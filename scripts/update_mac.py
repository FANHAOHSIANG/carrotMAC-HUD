import argparse
from datetime import datetime
import fcntl
import json
from pathlib import Path
import subprocess
import sys

from prepare_upstream import prepare
from mac_install import install_pair, restore_pair, run, revision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise ValueError('請在 Mac 執行更新／還原。')
    root = Path(__file__).resolve().parents[1]
    base = Path.home() / 'CarrotMacHUD'
    state = base / 'update'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(['pgrep', '-x', 'Jetlink'], stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError('請先退出 Jetlink App。')
        app = base / 'jetlink/macos/build/Jetlink.app'
        helper = base / 'carrot/tools/jetlink/mac_hud_supervisor.py'
        if args.rollback:
            info = json.loads((state / 'last-backup.json').read_text())
            backup = Path(info['backup'])
            if not backup.resolve().is_relative_to((base / 'backups').resolve()):
                raise ValueError('備份路徑不正確。')
            restore_pair(backup, app, helper)
            print('已還原 App 與 helper。')
            return
        versions = json.loads((root / 'versions.json').read_text())
        print(f"Mac App 將更新到 protocol {versions['protocol']}。C4 需包含 "
              f"{versions.get('comma_revision', versions['carrot_revision'])}；本工具不會更新 C4。", flush=True)
        if revision(base / 'carrot') != versions['carrot_revision']:
            raise ValueError('Carrot helper 原始碼版本不符，保留舊 App。')
        if not app.is_dir():
            raise ValueError('請先完成 v1 安裝。')
        candidate = root.parent / 'candidate-jetlink'
        prepare(root, candidate, versions['jetlink_revision'])
        new_helper = root / 'AppAutostart/mac_hud_supervisor.py'
        compile(new_helper.read_text(), str(new_helper), 'exec')
        import os
        env = dict(os.environ, CARROT_HUD_DIR=str(root.parent / 'test-hud-runtime'))
        run('swift', 'test', '--package-path', candidate / 'JetlinkKit', '--filter', 'CarrotHUDTests', env=env)
        for suite in ('ProtocolTests', 'ServerTests/', 'ServerHooksTests'):
            run('swift', 'test', '--package-path', candidate / 'JetlinkKit', '--filter', suite, env=env)
        run('make', '-C', candidate / 'macos', 'app')
        new_app = candidate / 'macos/build/Jetlink.app'
        run('codesign', '--verify', '--deep', '--strict', new_app)
        backup = base / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        install_pair(new_app, new_helper, app, helper, backup)
        (state / 'last-backup.json').write_text(json.dumps({'backup': str(backup), 'revision': versions['jetlink_revision']}))
        print(f'更新完成，舊版備份：{backup}\n之後直接開原本的修改版 Jetlink.app。')
        run('open', app.parent)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f'更新／還原停止：{error}', file=sys.stderr)
        sys.exit(1)
