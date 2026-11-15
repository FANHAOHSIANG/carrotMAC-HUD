"""Install the display patches on the pinned Mac HUD renderer."""

import argparse
import ast
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from mac_install import revision, run


RENDERER = 'openpilot/selfdrive/carrot/cluster/cluster_renderer.py'
GEAR_PATCH = 'carrot-hud-gear.patch'
NAV_LAYOUT_PATCH = 'carrot-hud-readable-nav.patch'


def relocate_gear_render_hunk(carrot, patch, temporary):
    """Refresh the context for the additive P/R hook, retaining strict checks elsewhere."""
    sections = re.split(r'(?m)(?=^diff --git )', patch.read_text(encoding='utf-8'))
    section = next(s for s in sections if s.startswith(f'diff --git a/{RENDERER} b/{RENDERER}\n'))
    hunks = re.split(r'(?m)(?=^@@ )', section)
    original = next(hunk for hunk in hunks if '+            self._gear_screens.draw(self, state, gear)\n' in hunk)
    header, *body = original.splitlines(keepends=True)
    hook = [line[1:] for line in body if line.startswith('+')]
    if any(line.startswith('-') for line in body) or not hook:
        raise ValueError('P／R 顯示補丁包含無法重新定位的變更。')

    source = (carrot / RENDERER).read_text(encoding='utf-8')
    tree = ast.parse(source, filename=RENDERER)
    renderer = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ClusterUiRenderer')
    render = next(node for node in renderer.body if isinstance(node, ast.FunctionDef) and node.name == 'render')
    if [arg.arg for arg in render.args.args[:2]] != ['self', 'state']:
        raise ValueError('無法辨識 Mac HUD 的 render 參數。')

    lines = source.splitlines(keepends=True)
    start = render.body[0].end_lineno if ast.get_docstring(render) is not None else render.body[0].lineno - 1
    end = start
    installed = next((i for i in range(start, render.end_lineno) if lines[i:i + len(hook)] == hook), None)
    if installed is not None:
        start, end = installed, installed + len(hook)
    else:
        names = {node.attr if isinstance(node, ast.Attribute) else node.id
                 for node in ast.walk(render) if isinstance(node, (ast.Name, ast.Attribute))}
        if names & {'gear_screen', '_gear_screens', '_ev6_park_screen_active', '_ev6_reverse_screen_active'}:
            raise ValueError('Mac HUD 的 P／R 顯示程式已另行修改。')
    updated = lines[:start] + (hook if installed is None else []) + lines[end:]
    compile(''.join(updated), RENDERER, 'exec')

    # Keep the shipped hunk's line hints and counts. Git uses the refreshed
    # surrounding lines to locate it, and still checks all other hunks verbatim.
    context = [line for line in body if line.startswith(' ')]
    if len(context) != 6 or start < 3 or len(lines) - end < 3:
        raise ValueError('無法辨識 Mac HUD 的 render 補丁位置。')
    adapted = header + ''.join(' ' + line for line in lines[start - 3:start])
    adapted += ''.join('+' + line for line in hook)
    adapted += ''.join(' ' + line for line in lines[end:end + 3])
    patch_path = Path(temporary) / patch.name
    patch_path.write_text(''.join(sections).replace(original, adapted, 1), encoding='utf-8')
    return patch_path


def apply_hud_patches(carrot, patches, rollback):
    command = ('git', '-C', carrot, 'apply')
    direction = ('--reverse',) if rollback else ()
    opposite = () if rollback else ('--reverse',)

    def applies(flags, patch):
        return subprocess.run([*command, *flags, '--check', patch], capture_output=True).returncode == 0

    layout_to_install = None
    if patches and patches[-1].name == NAV_LAYOUT_PATCH:
        layout = patches[-1]
        installed = applies(('--reverse',), layout)
        if rollback and installed:
            run(*command, '--reverse', layout)
            try:
                apply_hud_patches(carrot, patches[:-1], True)
            except (OSError, ValueError, subprocess.CalledProcessError):
                run(*command, layout)
                raise
            return True
        if not rollback and installed:
            return False
        if rollback:
            return apply_hud_patches(carrot, patches[:-1], True)
        layout_to_install = layout
        patches = patches[:-1]

    if tuple(patch.name for patch in patches[-2:]) == ('carrot-hud-nav-alerts.patch', 'carrot-hud-alert-placement.patch'):
        alerts, placement = patches[-2:]
        if rollback:
            # If the alert patch is absent, the dependent placement patch is absent too.
            if applies((), alerts):
                patches = patches[:-1]
        elif applies(('--reverse',), placement):
            # The later patch rewrites some of the earlier patch's hunks.
            patches = patches[:-2]
    if layout_to_install is not None:
        patches = (*patches, layout_to_install)

    applied = []
    with TemporaryDirectory(prefix='carrot-hud-patches-') as temporary:
        try:
            for patch in reversed(patches) if rollback else patches:
                if applies(opposite, patch):
                    continue
                if patch.name == GEAR_PATCH and not applies(direction, patch):
                    try:
                        patch = relocate_gear_render_hunk(carrot, patch, temporary)
                    except (StopIteration, SyntaxError) as error:
                        raise ValueError('無法辨識 Mac HUD 的 render 函式或補丁。') from error
                    if applies(opposite, patch):
                        continue
                run(*command, *direction, '--check', patch)
                run(*command, *direction, patch)
                applied.append(patch)
        except (OSError, ValueError, subprocess.CalledProcessError):
            for patch in reversed(applied):
                run(*command, *opposite, patch)
            raise
    return bool(applied)


def main():
    parser = argparse.ArgumentParser(description='更新或還原 Mac HUD 繁中、P／R 檔與導航提醒畫面')
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
    patches = tuple(overlays / name for name in (
        'carrot-hud-zh-tw.patch', GEAR_PATCH, 'carrot-hud-nav-clock.patch',
        'carrot-hud-nav-alerts.patch', 'carrot-hud-alert-placement.patch',
        NAV_LAYOUT_PATCH,
    ))
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
        print('Mac HUD 繁中、P／R 檔與導航提醒畫面更新完成。' if changed else 'Mac HUD 已是最新畫面版本。')
        print('重新開啟原本的 Jetlink App，HUD 會跟隨 C4 的語言設定。')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f'Mac HUD 更新停止：{error}')
