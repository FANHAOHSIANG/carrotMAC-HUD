"""Build a separate Jetlink candidate with read-only VLA replay UI."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import json
from prepare_upstream import prepare

def run(*args, **kw):
    subprocess.run([str(x) for x in args], check=True, **kw)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True, help='New candidate directory; never the installed App')
    a = p.parse_args()
    if sys.platform != 'darwin':
        p.error('Apple Silicon macOS and Xcode required')
    root = Path(__file__).resolve().parents[1]
    dest = a.output.expanduser().resolve()
    if dest.exists():
        p.error('Output must not exist')
    if subprocess.run(['pgrep','-x','Jetlink'],stdout=subprocess.DEVNULL).returncode == 0:
        p.error('Quit Jetlink before building')
    versions = json.loads((root/'versions.json').read_text())
    actual = prepare(root, dest, versions['jetlink_revision'])
    source = dest/'macos/Jetlink/App/JetlinkApp.swift'
    original = source.read_text()
    marker = '    CommandMenu("Server") {'
    if original.count(marker) != 1 or 'CommandMenu("VLA")' in original:
        raise ValueError('Upstream menu changed; refusing ambiguous patch')
    addition = (root/'tools/vla-metal/AppCommands.swift.fragment').read_text()
    source.write_text(original.replace(marker, addition + marker, 1))
    run(sys.executable, '-m', 'unittest', '-v', 'test_replay', cwd=root/'tools/vla-metal')
    env = dict(os.environ, JETLINK_VERSION=actual['jetlink_version'])
    run('make','-C',dest/'macos','app',env=env)
    app = dest/'macos/build/Jetlink.app'
    resources = app/'Contents/Resources/VLA-Offline'
    resources.mkdir(parents=True, exist_ok=False)
    for name in ('replay.py','test_replay.py','README.zh-TW.md','LICENSE.upstream'):
        shutil.copy2(root/'tools/vla-metal'/name,resources/name)
    run('make','-C',dest/'macos','sign',env=env)
    run('codesign','--verify','--deep','--strict',app)
    print(f'候選 App: {app}')
    print('僅供離線測試。沒有替換正式 App 或修改 C4。')

if __name__ == '__main__':
    main()
