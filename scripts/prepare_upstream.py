"""Resolve official JetLink, verify compatibility, and apply the HUD overlay."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


class CompatibilityError(ValueError):
    pass


def check_protocol(source, expected):
    match = re.search(r'protocolVersion\s*:\s*UInt16\s*=\s*(\d+)', source)
    if not match:
        raise CompatibilityError('找不到協定常數，需要人工適配。')
    actual = int(match[1])
    if actual != expected:
        raise CompatibilityError(f'官方 protocol {actual}，目前 HUD/Carrot 配對 protocol {expected}；保留現有版本。')


def run(*args):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True, text=True)


def prepare(root, destination, reference):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]*', reference):
        raise ValueError('無效的官方 ref。')
    if destination.exists():
        raise ValueError('候選資料夾已存在，請選擇空的路徑。')
    versions = json.loads((root / 'versions.json').read_text())
    run('git', 'init', destination)
    run('git', '-C', destination, 'remote', 'add', 'origin', 'https://github.com/zoompilot/jetlink.git')
    run('git', '-C', destination, 'fetch', '--depth', '1', 'origin', reference)
    run('git', '-C', destination, 'checkout', '--detach', 'FETCH_HEAD')
    sha = run('git', '-C', destination, 'rev-parse', 'HEAD').stdout.strip()
    pinned = destination / 'JetlinkKit/Sources/JetlinkKit/Pinned.swift'
    check_protocol(pinned.read_text(), versions['protocol'])
    for patch in (root / 'v1/jetlink-mac-hud.patch', root / 'AppAutostart/jetlink-autostart.patch'):
        run('git', '-C', destination, 'apply', '--check', patch)
        run('git', '-C', destination, 'apply', patch)
    versions['jetlink_revision'] = sha
    return versions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ref', required=True)
    parser.add_argument('--destination', type=Path, default=Path('candidate-jetlink'))
    parser.add_argument('--report', type=Path, default=Path('upstream-report.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        versions = prepare(root, args.destination.resolve(), args.ref)
        report = {'status': 'ready', 'versions': versions, 'message': '補丁與協定檢查通過；尚待 Mac 編譯與實機驗證。'}
        (root / 'candidate-versions.json').write_text(json.dumps(versions, indent=2) + '\n')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        report = {'status': 'blocked', 'message': str(detail).strip()}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(report['message'], flush=True)
    # A blocked candidate is a successful compatibility check, not an update.
    return 0


if __name__ == '__main__':
    sys.exit(main())
