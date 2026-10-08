"""Fetch the pinned official C4 source, apply the overlay and run CPU checks."""
import ast
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', REPO / 'scripts/install_c4_parked.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def main():
  with tempfile.TemporaryDirectory(prefix='carrot-parked-check-') as directory:
    root = Path(directory) / 'source'
    baseline = Path(directory) / 'baseline'
    paths = installer.FILES[:-1] + ['openpilot/common/jetlink_peer.py']
    for name in paths:
      url = f'https://raw.githubusercontent.com/ajouatom/openpilot/{installer.BASE}/{name}'
      with urllib.request.urlopen(url, timeout=30) as response:
        content = response.read().decode('utf-8')
      target = root / name
      target.parent.mkdir(parents=True, exist_ok=True)
      target.write_text(content)
    shutil.copytree(root, baseline)
    installer.run('git', '-C', root, 'init', '-q')
    installer.run('git', '-C', root, 'add', '.')
    installer.run('git', '-C', root, 'apply', '--check', installer.PATCH)
    installer.run('git', '-C', root, 'apply', installer.PATCH)
    for name in installer.FILES:
      ast.parse((root / name).read_text(), filename=name)
    expected = REPO / 'overlays/protocol3/parked-switch/parked.py'
    assert expected.read_bytes() == (root / installer.FILES[-1]).read_bytes(), 'Published guard and patch diverged'
    installer.run('git', '-C', root, 'diff', '--check')
    installer.run(sys.executable, REPO / 'scripts/test_c4_parked.py', env=dict(os.environ, C4_SOURCE_ROOT=str(root)))
    installer.run(sys.executable, '-m', 'unittest', 'discover', '-s', str(REPO / 'tests'), '-p', 'test_c4_installer.py', '-v',
                  env=dict(os.environ, C4_BASELINE_ROOT=str(baseline)))
    print('Pinned official C4 patch, syntax and parked-switch CPU checks passed. Hardware remains unvalidated.')


if __name__ == '__main__':
  main()
