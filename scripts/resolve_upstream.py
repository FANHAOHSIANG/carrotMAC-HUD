"""Select an immutable official release; unchanged scheduled checks skip Mac builds."""
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

REPOSITORY = 'https://github.com/zoompilot/jetlink.git'
RELEASE_API = 'https://api.github.com/repos/zoompilot/jetlink/releases/latest'


def stable_tag(release):
    tag = release.get('tag_name', '')
    if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise ValueError('Official latest release is not a stable semantic version.')
    return tag


def peeled_tag(output, tag):
    refs = {}
    for line in output.splitlines():
        sha, ref = line.split()
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('Invalid upstream SHA.')
        refs[ref] = sha
    sha = refs.get(f'refs/tags/{tag}^{{}}', refs.get(f'refs/tags/{tag}'))
    if sha is None:
        raise ValueError('Official release tag was not found.')
    return sha


def resolve(versions, event, reference='', release_loader=None, tag_loader=None):
    if event in ('push', 'pull_request'):
        return {'ref': versions['jetlink_revision'], 'prepare': True, 'promote': False}
    reference = reference or 'latest'
    if reference != 'latest':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]*', reference):
            raise ValueError('Invalid upstream ref.')
        return {'ref': reference, 'prepare': True, 'promote': False}
    tag = stable_tag((release_loader or fetch_release)())
    sha = (tag_loader or fetch_tag)(tag)
    return {'ref': sha, 'release': tag, 'prepare': sha != versions['jetlink_revision'], 'promote': True}


def fetch_release():
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'CarrotMacHUD-release-sync'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(RELEASE_API, headers=headers), timeout=20) as response:
        return json.load(response)


def fetch_tag(tag):
    output = subprocess.run(['git', 'ls-remote', REPOSITORY, f'refs/tags/{tag}', f'refs/tags/{tag}^{{}}'],
                            check=True, capture_output=True, text=True).stdout
    return peeled_tag(output, tag)


def main():
    versions = json.loads(Path('versions.json').read_text())
    selection = resolve(versions, os.environ.get('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                        os.environ.get('UPSTREAM_REF', 'latest'))
    Path('upstream-selection.json').write_text(json.dumps(selection, indent=2) + '\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key in ('ref', 'prepare', 'promote'):
            value = selection[key]
            print(f'{key}={str(value).lower() if isinstance(value, bool) else value}', file=output)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        print('Official selection: ' + selection.get('release', selection['ref']), file=summary)
        if not selection['prepare']:
            print('Already synchronized; no Mac build needed.', file=summary)


if __name__ == '__main__':
    main()
