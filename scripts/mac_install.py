"""Build a HUD fork in isolation, then install or restore a matched App/helper."""
import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

BASE = Path.home() / 'CarrotMacHUD'


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def revision(repo):
    return run('git', '-C', repo, 'rev-parse', 'HEAD', capture_output=True, text=True).stdout.strip()


def replace_helper(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + '.update-tmp')
    try:
        shutil.copy2(source, pending)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)


def restore_pair(backup, app, helper):
    # Stage a full App copy first; do not discard the running installation.
    pending = app.with_name('Jetlink.restore-tmp.app')
    old = app.with_name('Jetlink.restore-old.app')
    if pending.exists() or old.exists():
        raise ValueError('發現先前中斷的還原檔案，請保留並檢查 build 資料夾。')
    run('ditto', backup / 'Jetlink.app', pending)
    moved = False
    try:
        if app.exists():
            app.rename(old)
            moved = True
        pending.rename(app)
        if (backup / 'mac_hud_supervisor.py').exists():
            replace_helper(backup / 'mac_hud_supervisor.py', helper)
        else:
            helper.unlink(missing_ok=True)
    except Exception:
        if moved:
            if app.exists():
                shutil.rmtree(app)
            old.rename(app)
        raise
    finally:
        if pending.exists():
            shutil.rmtree(pending)
    if old.exists():
        shutil.rmtree(old)


def install_pair(new_app, new_helper, app, helper, backup):
    backup.mkdir(parents=True)
    run('ditto', app, backup / 'Jetlink.app')
    if helper.exists():
        shutil.copy2(helper, backup / 'mac_hud_supervisor.py')
    pending = app.with_name('Jetlink.update-tmp.app')
    old = app.with_name('Jetlink.update-old.app')
    if pending.exists() or old.exists():
        raise ValueError('發現先前中斷的更新檔案，請保留並檢查 build 資料夾。')
    run('ditto', new_app, pending)
    changed = False
    try:
        app.rename(old)
        changed = True
        pending.rename(app)
        replace_helper(new_helper, helper)
    except Exception:
        if changed:
            if app.exists():
                shutil.rmtree(app)
            old.rename(app)
            if (backup / 'mac_hud_supervisor.py').exists():
                replace_helper(backup / 'mac_hud_supervisor.py', helper)
            else:
                helper.unlink(missing_ok=True)
        raise
    finally:
        if pending.exists():
            shutil.rmtree(pending)
    shutil.rmtree(old)


