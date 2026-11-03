"""Restore the live model path in the Mac HUD only, with backup/rollback."""
import argparse
import ast
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import install_nav_preview as common

LIVE = 'openpilot/selfdrive/carrot/cluster/cluster_live.py'
MODULE = 'tools/jetlink/cluster_nav_line.py'
FILES = (LIVE,)


def patch_live(source):
    tree = ast.parse(source)
    matches = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
               and n.name == '_with_external_nav_route']
    if len(matches) != 1:
        raise ValueError('無法辨識 HUD 路線替換函式，保留原檔。')
    method = matches[0]
    replacement = "    def _with_external_nav_route(self, state: ClusterUiState) -> ClusterUiState:\n        # Keep the live model path on the driving view; navigation stays in the map.\n        return state\n"
    lines = source.splitlines(keepends=True)
    lines[method.lineno - 1:method.end_lineno] = [replacement]
    result = ''.join(lines)
    compile(result, LIVE, 'exec')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path.home() / 'CarrotMacHUD')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin' or (args.check and args.rollback):
        raise ValueError('請在 Mac 執行，檢查與還原不可同時使用。')
    base = args.base.resolve()
    helper = base / 'carrot'
    state = base / 'update'
    state.mkdir(parents=True, exist_ok=True)
    common.FILES = FILES
    with (state / 'update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not args.check and subprocess.run(
                ['pgrep', '-f', r'(^|/)(Jetlink|hud\.py|mac_hud_supervisor\.py)( |$)'],
                stdout=subprocess.DEVNULL).returncode == 0:
            raise ValueError('請先退出 Jetlink App 與 HUD helper。')
        pointer = state / 'model-path-backup.json'
        if args.rollback:
            backup = Path(json.loads(pointer.read_text())['backup']).resolve()
            if not backup.is_relative_to((base / 'backups').resolve()):
                raise ValueError('備份路徑不正確。')
            manifest = json.loads((backup / 'manifest.json').read_text())
            for name in FILES:
                if not (helper / name).is_file() or hashlib.sha256((helper / name).read_bytes()).hexdigest() != manifest['installed_sha256'][name]:
                    raise ValueError('檔案已另行變更，停止還原。')
            common.restore(helper, backup)
            pointer.unlink()
            print('已還原藍線顯示。')
            return
        with tempfile.TemporaryDirectory(dir=state, prefix='model-path-') as directory:
            staged = Path(directory)
            target = staged / LIVE
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(patch_live((helper / LIVE).read_text()))
            if args.check:
                print('藍線顯示修正相容性檢查通過。')
                return
            backup = base / 'backups' / ('model-path-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            common.install(helper, staged, backup)
            try:
                pending = pointer.with_suffix('.tmp')
                pending.write_text(json.dumps({'backup': str(backup)}))
                pending.replace(pointer)
            except BaseException:
                common.restore(helper, backup)
                raise
        print('已恢復 Mac HUD 模型行駛路徑，右側地圖保留。備份：' + str(backup))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print('藍線更新停止：' + str(error), file=sys.stderr)
        sys.exit(1)
