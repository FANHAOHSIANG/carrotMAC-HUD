"""Stage and back up the small mode-7 helper overlay without replacing a venv."""
import json
from pathlib import Path
import shutil
import subprocess

FILES = ('openpilot/selfdrive/carrot/cluster/cluster_config.py',
         'openpilot/selfdrive/carrot/cluster/cluster_renderer.py',
         'tools/jetlink/hud_map_receiver.py')


def prepare_map_helper(root, helper_root, stage):
    stage.mkdir(parents=True, exist_ok=False)
    for name in FILES[:2]:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(helper_root / name, target)
    patch = root / 'overlays/map-channel/mac-renderer.patch'
    check = subprocess.run(['git', '-C', str(stage), 'apply', '--check', str(patch)], capture_output=True, text=True)
    if check.returncode == 0:
        subprocess.run(['git', '-C', str(stage), 'apply', str(patch)], check=True)
    else:
        reverse = subprocess.run(['git', '-C', str(stage), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
        if reverse.returncode:
            raise ValueError('Mac 模式 7 renderer 補丁不相容，保留現有 App/helper：' + check.stderr)
    target = stage / FILES[2]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / 'overlays/map-channel/hud_map_receiver.py', target)
    for name in FILES:
        compile((stage / name).read_text(), name, 'exec')
    return stage


def install_map_helper(stage, helper_root, backup):
    saved = backup / 'map-helper'
    saved.mkdir()
    present = []
    for name in FILES:
        source = helper_root / name
        if source.exists():
            target = saved / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            present.append(name)
    (saved / 'manifest.json').write_text(json.dumps(present))
    try:
        from mac_install import replace_helper
        for name in FILES:
            replace_helper(stage / name, helper_root / name)
    except Exception:
        restore_map_helper(helper_root, backup)
        raise


def restore_map_helper(helper_root, backup):
    saved = backup / 'map-helper'
    if not (saved / 'manifest.json').exists():
        return
    from mac_install import replace_helper
    present = json.loads((saved / 'manifest.json').read_text())
    for name in FILES:
        if name in present:
            replace_helper(saved / name, helper_root / name)
        else:
            (helper_root / name).unlink(missing_ok=True)
