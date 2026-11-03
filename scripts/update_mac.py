import argparse
from datetime import datetime
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from install_model_path import LIVE, patch_live
from drive_install import install_bundle, restore_bundle

from prepare_upstream import prepare
from mac_install import install_pair, restore_pair, run, revision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--drive-fixes', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise ValueError('請在 Mac 執行更新／還原。')
    root = Path(__file__).resolve().parents[1]
    base = Path.home() / 'CarrotMacHUD'
    state = base / 'update'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(['pgrep', '-f', r'(^|/)(Jetlink|hud\.py|mac_hud_supervisor\.py)( |$)'],
                          stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError('請先退出 Jetlink App。')
        app = base / 'jetlink/macos/build/Jetlink.app'
        helper = base / 'carrot/tools/jetlink/mac_hud_supervisor.py'
        if args.rollback:
            info = json.loads((state / 'last-backup.json').read_text())
            backup = Path(info['backup'])
            if not backup.resolve().is_relative_to((base / 'backups').resolve()):
                raise ValueError('備份路徑不正確。')
            if (backup / 'drive-fixes.json').exists():
                restore_bundle(backup, app, helper, base / 'carrot' / LIVE)
            else:
                restore_pair(backup, app, helper)
            print('已還原 App 與 helper。')
            return
        versions = json.loads((root / 'versions.json').read_text())
        print(f"Mac App 將更新到 JetLink {versions.get('jetlink_version', '固定版')}，protocol {versions['protocol']}。C4 需包含 "
              f"{versions.get('comma_revision', versions['carrot_revision'])}；本工具不會更新 C4。", flush=True)
        if revision(base / 'carrot') != versions['carrot_revision']:
            raise ValueError('Carrot helper 原始碼版本不符，保留舊 App。')
        if not app.is_dir():
            raise ValueError('請先完成 v1 安裝。')
        live = base / 'carrot' / LIVE
        original_live = live.read_bytes() if args.drive_fixes else None
        patched_live = patch_live(original_live.decode()) if args.drive_fixes else None
        candidate = root.parent / 'candidate-jetlink'
        prepare(root, candidate, versions['jetlink_revision'])
        run(sys.executable, root / 'scripts/check_nav_contract.py', candidate)
        new_helper = root / 'AppAutostart/mac_hud_supervisor.py'
        compile(new_helper.read_text(), str(new_helper), 'exec')
        import os
        env = dict(os.environ, CARROT_HUD_DIR=str(root.parent / 'test-hud-runtime'),
                   JETLINK_VERSION=versions['jetlink_version'])
        run('swift', 'test', '--package-path', candidate / 'JetlinkKit', '--filter', 'CarrotHUDTests', env=env)
        for suite in ('SpecTests', 'ProtocolTests', 'ServerTests/', 'ServerHooksTests'):
            run('swift', 'test', '--package-path', candidate / 'JetlinkKit', '--filter', suite, env=env)
        run('make', '-C', candidate / 'macos', 'app', env=env)
        new_app = candidate / 'macos/build/Jetlink.app'
        run('codesign', '--verify', '--deep', '--strict', new_app)
        backup = base / 'backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        # Building can take minutes: recheck processes and the renderer before
        # replacing anything, rather than relying on the initial preflight.
        if subprocess.run(['pgrep', '-f', r'(^|/)(Jetlink|hud\.py|mac_hud_supervisor\.py)( |$)'],
                          stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError('編譯期間 App/HUD 已啟動，保留原安裝；請退出後重試。')
        if args.drive_fixes:
            if live.read_bytes() != original_live:
                raise ValueError('編譯期間模型路徑檔案已變更，保留原安裝。')
            with tempfile.TemporaryDirectory(dir=state, prefix='drive-fixes-') as directory:
                staged = Path(directory) / 'cluster_live.py'
                staged.write_text(patched_live)
                install_bundle(new_app, new_helper, app, helper, live, staged, backup)
        else:
            install_pair(new_app, new_helper, app, helper, backup)
        pending = state / 'last-backup.json.tmp'
        try:
            pending.write_text(json.dumps({'backup': str(backup), 'revision': versions['jetlink_revision'],
                                           'overlay_revision': revision(root), 'drive_fixes': args.drive_fixes}))
            pending.replace(state / 'last-backup.json')
        except BaseException:
            if args.drive_fixes:
                restore_bundle(backup, app, helper, live)
            else:
                restore_pair(backup, app, helper)
            raise
        finally:
            pending.unlink(missing_ok=True)
        if args.drive_fixes:
            print('已整合安裝 Mac N16 無損傳輸與模型路徑顯示修正；地圖接收端保留。')
            print('C4 也需安裝配對提交，啟用後檢查 execution.compact_reply=true。')
        print(f'更新完成，舊版備份：{backup}\n之後直接開原本的修改版 Jetlink.app。')
        run('open', app.parent)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as error:
        print(f'更新／還原停止：{error}', file=sys.stderr)
        sys.exit(1)
