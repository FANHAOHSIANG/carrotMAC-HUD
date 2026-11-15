"""On Mac CI, prove the regression tests fail before and pass after the patch."""
import argparse
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if not (source / 'JetlinkKit/Tests/JetlinkServerTests/MacRuntimeTests.swift').exists():
        print('Runtime patch does not apply to this release.')
        return
    if sys.platform != 'darwin':
        raise RuntimeError('The Mac read-window regression must run on macOS.')
    patch = Path(__file__).resolve().parents[1] / 'overlays/protocol3/jetlink-mac-runtime.patch'
    apply = ['git', '-C', str(source), 'apply',
             '--include=JetlinkKit/Sources/JetlinkServer/EngineHost.swift',
             '--include=JetlinkKit/Sources/JetlinkServer/ReadRing.swift']
    command = ['swift', 'test', '--package-path', str(source / 'JetlinkKit'),
               '--arch', 'arm64', '--filter', 'MacRuntimeTests']
    subprocess.run([*apply, '--reverse', '--check', str(patch)], check=True)
    subprocess.run([*apply, '--reverse', str(patch)], check=True)
    try:
        baseline = subprocess.run(command, capture_output=True, text=True, timeout=600)
        output = baseline.stdout + baseline.stderr
        print(output, flush=True)
        # Compilation failures, unrelated exceptions and zero matching tests
        # must not be mistaken for reproducing the two intended failures.
        if (baseline.returncode == 0
                or not re.search(r'Test run with 2 tests[^\n]*failed', output)
                or 'backend.builds.all.count' not in output
                or 'kernel.buffered' not in output):
            raise RuntimeError('Did not reproduce BOTH expected runtime assertions on the baseline.')
        print('Confirmed: unpatched source fails both runtime regression assertions.', flush=True)
    finally:
        subprocess.run([*apply, str(patch)], check=True)
    subprocess.run(command, check=True, timeout=600)
    print('Confirmed: patched source passes the same runtime regression tests.', flush=True)


if __name__ == '__main__':
    main()
