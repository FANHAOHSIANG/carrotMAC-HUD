"""Permit automatic promotion to change only the tested JetLink revision/version."""
import json
from pathlib import Path
import re

ALLOWED = {'jetlink_revision', 'jetlink_version'}


def validate(current, candidate):
    if {k: v for k, v in current.items() if k not in ALLOWED} != {k: v for k, v in candidate.items() if k not in ALLOWED}:
        raise ValueError('Automatic sync cannot change protocol, renderer, C4 pairing or schema.')
    if not re.fullmatch(r'[0-9a-f]{40}', candidate.get('jetlink_revision', '')):
        raise ValueError('Candidate revision is invalid.')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', candidate.get('jetlink_version', '')):
        raise ValueError('Candidate product version is invalid.')


def main():
    current = json.loads(Path('versions.json').read_text())
    candidate = json.loads(Path('candidate-versions.json').read_text())
    selection = json.loads(Path('upstream-selection.json').read_text())
    validate(current, candidate)
    if not selection.get('promote') or candidate['jetlink_revision'] != selection['ref']:
        raise ValueError('Candidate does not match the resolved official release.')
    if 'v' + candidate['jetlink_version'] != selection['release']:
        raise ValueError('Product version does not match the official release tag.')
    Path('versions.json').write_text(json.dumps(candidate, indent=2) + '\n')


if __name__ == '__main__':
    main()
