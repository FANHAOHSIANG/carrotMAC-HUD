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
NAV_TEXT_ROUTE_PATCH = 'carrot-hud-nav-text-route.patch'
ALERT_POSITION_PATCH = 'carrot-hud-alert-positions.patch'
MODE7_MAP_PATCH = 'carrot-hud-mode7-map.patch'


NATIVE_MODE7 = '''            if screen_mode == CLUSTER_SCREEN_MODE_NAV_MODEL:
                self._draw_driving_hud_content(state, screen_mode, left_signal_lit, right_signal_lit)
                self._draw_nav_model_map()
                self._draw_status_footer(state)
                return
'''
NATIVE_MODE7_HEADER = '            if screen_mode == CLUSTER_SCREEN_MODE_NAV_MODEL:\n'


def adapt_native_mode7(carrot, patches, temporary):
    source = (carrot / RENDERER).read_text(encoding='utf-8')
    if NATIVE_MODE7_HEADER not in source:
        return patches

    adapted = []
    for patch in patches:
        if patch.name == NAV_LAYOUT_PATCH:
            body = patch.read_text(encoding='utf-8')
            # The native mode-7 branch follows the assignment on both sides of the patch.
            old = '             if screen_mode == CLUSTER_SCREEN_MODE_NAVI:\n'
            head, tail = body.split(old, 1)
            context = ''.join(' ' + line for line in NATIVE_MODE7.splitlines(keepends=True))
            body = head.replace('@@ -3850,8 +3850,8 @@', '@@ -3850,13 +3850,13 @@', 1) + context + old + tail
        elif patch.name == MODE7_MAP_PATCH:
            body = patch.read_text(encoding='utf-8')
            header = f'diff --git a/{RENDERER} b/{RENDERER}\n'
            section = body[body.index(header):]
            index = section.index('@@ -3854,')
            next_hunk = section.index('@@ ', section.index('\n', index) + 1)
            file_header = section[:section.index('@@ ')]
            new_call = (
                '                if (getattr(state, "navi_live", None) is not None\n'
                '                        or getattr(state, "external_nav_active", False)):\n'
                '                    self._draw_mode7_map_card(state)\n'
                '                else:\n'
                '                    self._draw_nav_model_map()\n'
            )
            before_call = '                self._draw_nav_model_map()\n'
            context_head, context_tail = NATIVE_MODE7.split(before_call)
            # Keep the installation's existing mode-7 constant, config and world-view positioning.
            hunk = '@@ -3857,8 +3857,12 @@ class ClusterUiRenderer:\n'
            hunk += ''.join(' ' + line for line in context_head.splitlines(keepends=True))
            hunk += '-' + before_call
            hunk += ''.join('+' + line for line in new_call.splitlines(keepends=True))
            context_tail += '            if screen_mode == CLUSTER_SCREEN_MODE_NAVI:\n'
            context_tail += '                self._draw_navi_dashboard(state)\n'
            context_tail += '                self._draw_status_footer(state)\n'
            hunk += ''.join(' ' + line for line in context_tail.splitlines(keepends=True))
            body = file_header + hunk + section[next_hunk:]
        else:
            adapted.append(patch)
            continue
        output = Path(temporary) / patch.name
        output.write_text(body, encoding='utf-8')
        adapted.append(output)
    return tuple(adapted)


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
    with TemporaryDirectory(prefix='carrot-hud-mode7-') as temporary:
        patches = adapt_native_mode7(carrot, patches, temporary)
        return _apply_hud_patches(carrot, patches, rollback)


def _apply_hud_patches(carrot, patches, rollback):
    command = ('git', '-C', carrot, 'apply')
    direction = ('--reverse',) if rollback else ()
    opposite = () if rollback else ('--reverse',)

    def applies(flags, patch):
        return subprocess.run([*command, *flags, '--check', patch], capture_output=True).returncode == 0

    # Later overlays replace hunks from earlier ones, so unwind them first.
    layers_to_install = []
    while patches and patches[-1].name in (NAV_LAYOUT_PATCH, NAV_TEXT_ROUTE_PATCH, MODE7_MAP_PATCH, ALERT_POSITION_PATCH):
        layout = patches[-1]
        installed = applies(('--reverse',), layout)
        if rollback and installed:
            run(*command, '--reverse', layout)
            try:
                _apply_hud_patches(carrot, patches[:-1], True)
            except (OSError, ValueError, subprocess.CalledProcessError):
                run(*command, layout)
                raise
            return True
        if not rollback and installed:
            patches = ()
            break
        if rollback:
            return _apply_hud_patches(carrot, patches[:-1], True)
        layers_to_install.append(layout)
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
    patches = (*patches, *reversed(layers_to_install))

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
        NAV_LAYOUT_PATCH, NAV_TEXT_ROUTE_PATCH, MODE7_MAP_PATCH, ALERT_POSITION_PATCH,
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
