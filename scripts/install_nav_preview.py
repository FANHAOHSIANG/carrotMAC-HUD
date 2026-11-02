"""Install the display-only PNG receiver, preserving the App and model runtime."""
import argparse
import ast
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RENDERER = 'openpilot/selfdrive/carrot/cluster/cluster_renderer.py'
CONFIG = 'openpilot/selfdrive/carrot/cluster/cluster_config.py'
RECEIVER = 'tools/jetlink/hud_map_receiver.py'
FILES = (RENDERER, CONFIG, RECEIVER)


def receiver_renderer(source):
    tree = ast.parse(source)
    method = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                   and n.name == '_draw_nav_model_map'), None)
    if method is None:
        raise ValueError('HUD renderer 尚未支援模式 7。')
    lines = source.splitlines(keepends=True)
    block = ''.join(lines[method.lineno - 1:method.end_lineno])
    old = 'from openpilot.selfdrive.navigation.preview import PREVIEW_PATH, preview_fresh'
    if old in block and 'self._nav_model_fresh = preview_fresh()' in block:
        block = block.replace(old, 'from hud_map_receiver import preview', 1)
        block = block.replace('self._nav_model_fresh = preview_fresh()',
                              'PREVIEW_PATH, self._nav_model_fresh = preview()', 1)
    elif not ('from hud_map_receiver import preview' in block and
              'PREVIEW_PATH, self._nav_model_fresh = preview()' in block):
        raise ValueError('無法辨識這版 HUD 地圖 renderer；保留原檔。')
    lines[method.lineno - 1:method.end_lineno] = [block]
    result = ''.join(lines)
    compile(result, RENDERER, 'exec')
    return result


def stage(helper, target):
    for name in (RENDERER, CONFIG):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(helper / name, destination)
    source = (target / RENDERER).read_text()
    if not any(isinstance(n, ast.FunctionDef) and n.name == '_draw_nav_model_map'
               for n in ast.walk(ast.parse(source))):
        # The original pinned Mac helper predates mode 7. Use the existing
        # display-only layout patch, without its obsolete JPEG transport.
        patch = ROOT / 'overlays/nav-preview/legacy-mode7.patch'
        subprocess.run(['git', '-C', str(target), 'apply', '--check', str(patch)], check=True)
        subprocess.run(['git', '-C', str(target), 'apply', str(patch)], check=True)
        source = (target / RENDERER).read_text()
    (target / RENDERER).write_text(receiver_renderer(source))
    destination = target / RECEIVER
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'overlays/nav-preview/hud_map_receiver.py', destination)
    for name in FILES:
        compile((target / name).read_text(), name, 'exec')


def replace(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + '.nav-preview-tmp')
    try:
        shutil.copy2(source, pending)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)


def restore(helper, backup):
    manifest = json.loads((backup / 'manifest.json').read_text())
    for name in FILES:
        if manifest['present'][name]:
            replace(backup / name, helper / name)
        else:
            (helper / name).unlink(missing_ok=True)


def install(helper, staged, backup):
    backup.mkdir(parents=True, exist_ok=False)
    manifest = {'present': {}, 'installed_sha256': {}}
    for name in FILES:
        source = helper / name
        manifest['present'][name] = source.exists()
        if source.exists():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, saved)
        manifest['installed_sha256'][name] = hashlib.sha256((staged / name).read_bytes()).hexdigest()
    (backup / 'manifest.json').write_text(json.dumps(manifest))
    try:
        for name in FILES:
            replace(staged / name, helper / name)
    except BaseException:
        restore(helper, backup)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path.home() / 'CarrotMacHUD')
    parser.add_argument('--check', action='store_true', help='驗證相容性，不修改安裝')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise ValueError('請在 Mac 執行。')
    if args.check and args.rollback:
        raise ValueError('--check 與 --rollback 不可同時使用。')
    base = args.base.resolve()
    helper = base / 'carrot'
    state = base / 'update'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not args.check and subprocess.run(
                ['pgrep', '-f', r'(^|/)(Jetlink|hud\.py|mac_hud_supervisor\.py)( |$)'],
                stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError('請先退出 Jetlink App，並停止舊 HUD helper，再執行安裝。')
        pointer = state / 'nav-preview-backup.json'
        if args.rollback:
            backup = Path(json.loads(pointer.read_text())['backup']).resolve()
            if not backup.is_relative_to((base / 'backups').resolve()):
                raise ValueError('備份路徑不正確。')
            manifest = json.loads((backup / 'manifest.json').read_text())
            for name in FILES:
                if not (helper / name).is_file() or hashlib.sha256((helper / name).read_bytes()).hexdigest() != manifest['installed_sha256'][name]:
                    raise ValueError('安裝後檔案已變更；停止還原以保留後續修改。')
            restore(helper, backup)
            pointer.unlink()
            print('已還原地圖 helper；App 與模型未變更。')
            return
        from PIL import Image  # Validate the installed HUD Python environment first.
        for name in ('hud.py', 'hud_runtime.py', 'hud_protocol.py'):
            if not (helper / 'tools/jetlink' / name).is_file():
                raise ValueError('找不到既有 Mac HUD 環境：' + name)
        if 'received = now - age' not in (helper / 'tools/jetlink/hud_protocol.py').read_text():
            raise ValueError('Mac snapshot 時鐘轉換不相容；保留安裝。')
        with tempfile.TemporaryDirectory(prefix='nav-preview-', dir=state) as temporary:
            staged = Path(temporary)
            stage(helper, staged)
            if args.check:
                print('相容性檢查通過，可以安裝官方 PNG 地圖接收端。')
                return
            backup = base / 'backups' / ('nav-preview-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            install(helper, staged, backup)
            try:
                pending = pointer.with_suffix('.tmp')
                pending.write_text(json.dumps({'backup': str(backup)}))
                os.replace(pending, pointer)
            except BaseException:
                restore(helper, backup)
                raise
        print('已安裝官方 PNG 地圖接收端。App、Jetlink 版本與模型未變更。')
        print('C4 也需安裝配對的 Mac nav_map 發送修正；HUD 顯示模式選 7。')
        print('備份：' + str(backup))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ImportError, KeyError, subprocess.CalledProcessError) as error:
        print('地圖更新停止：' + str(error), file=sys.stderr)
        sys.exit(1)
