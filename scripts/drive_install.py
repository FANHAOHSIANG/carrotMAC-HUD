"""Install/restore the App, supervisor and model-path renderer as one bundle."""
import hashlib
import json
from pathlib import Path
import shutil

from mac_install import install_pair, restore_pair, replace_helper


def install_bundle(new_app, new_helper, app, helper, live, patched, backup):
    original = live.read_bytes()
    installed = False
    try:
        install_pair(new_app, new_helper, app, helper, backup)
        installed = True
        # Keep the exact pre-existing helper, including earlier local patches.
        saved = backup / 'cluster_live.py'
        saved.write_bytes(original)
        shutil.copymode(live, saved)
        (backup / 'drive-fixes.json').write_text(json.dumps({
            'live': str(live.resolve()),
            'before_sha256': hashlib.sha256(original).hexdigest(),
            'installed_sha256': hashlib.sha256(patched.read_bytes()).hexdigest(),
        }))
        replace_helper(patched, live)
    except BaseException:
        if installed:
            saved = backup / 'cluster_live.py'
            if saved.exists():
                replace_helper(saved, live)
            restore_pair(backup, app, helper)
        raise


def restore_bundle(backup, app, helper, expected_live):
    info = json.loads((backup / 'drive-fixes.json').read_text())
    live = Path(info['live'])
    saved = backup / 'cluster_live.py'
    if (live.resolve() != expected_live.resolve() or
        hashlib.sha256(live.read_bytes()).hexdigest() != info['installed_sha256'] or
        hashlib.sha256(saved.read_bytes()).hexdigest() != info['before_sha256']):
        raise ValueError('模型路徑檔案已另行變更或備份不符，停止還原。')
    # Stage the old renderer first. If the App restore fails, preserve the
    # current renderer so the installed bundle stays paired.
    current = live.with_name(live.name + '.drive-restore-current')
    if current.exists():
        raise ValueError('發現中斷的模型路徑還原檔案，停止還原。')
    shutil.copy2(live, current)
    try:
        replace_helper(saved, live)
        try:
            restore_pair(backup, app, helper)
        except BaseException:
            replace_helper(current, live)
            raise
    finally:
        current.unlink(missing_ok=True)
