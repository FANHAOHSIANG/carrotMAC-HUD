"""Download one complete recorded ROAD segment from a user-supplied Carrot route URL.
No embedded device identifiers or route URLs; no uploads or vehicle access.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, unquote
from urllib.request import build_opener, HTTPRedirectHandler, Request

MAX_FILE = 512 * 1024**2
MAX_MANIFEST = 4 * 1024**2
LOGS = ('rlog.zst', 'rlog.bz2', 'rlog')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def base_url(url):
    p = urlsplit(url.strip().rstrip('/'))
    if (p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment
            or not re.fullmatch(r'/routes/[^/]+/[^/]+', p.path)):
        raise ValueError('Expected an HTTPS Carrot route selection URL (/routes/.../...)')
    return p.geturl()

def choose(manifest, base):
    if not isinstance(manifest, dict) or manifest.get('ok') is not True:
        raise ValueError('Invalid route manifest')
    candidates = []
    origin = urlsplit(base)
    prefix = unquote(origin.path) + '/files/'
    for segment in manifest.get('segments', []):
        index = segment.get('index')
        if type(index) is not int or not 0 <= index <= 1000000:
            continue
        files = {f['name']: f for f in segment.get('files', []) if isinstance(f, dict) and 'name' in f}
        log_names = [n for n in LOGS if n in files]
        camera = next((n for n in ('fcamera.hevc','qcamera.ts') if n in files), None)
        if not log_names or camera is None:
            continue
        pair = [files[log_names[0]], files[camera]]
        for f in pair:
            p = urlsplit(f['url'])
            path = unquote(p.path)
            if ((p.scheme, p.netloc) != (origin.scheme, origin.netloc)
                    or p.query or p.fragment or not path.startswith(prefix)
                    or not path.endswith(f"/{index}/{f['name']}")
                    or any(x in ('.','..') for x in path.split('/'))
                    or type(f.get('size')) is not int or not 0 < f['size'] <= MAX_FILE):
                raise ValueError('Unexpected route file URL or size')
        candidates.append((index, pair))
    if not candidates:
        raise ValueError('找不到同時含 rlog 與 fcamera.hevc 或 qcamera.ts 的片段。')
    return sorted(candidates, key=lambda c: (c[1][1]['name'] != 'fcamera.hevc', c[0]))

def download(opener, entry, out):
    destination = out / entry['name']
    temporary = destination.with_suffix(destination.suffix + '.part')
    expected = entry['size']
    count = 0
    try:
        with opener.open(Request(entry['url'], headers={'Accept-Encoding':'identity'}), timeout=60) as response:
            if response.headers.get_content_type() in ('text/html','application/json'):
                raise ValueError('Received HTML/JSON instead of a recorded file')
            with temporary.open('xb') as f:
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > expected:
                        raise ValueError('File larger than manifest')
                    f.write(chunk)
        if count != expected:
            raise ValueError('File length differs from manifest')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--route-url', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    from replay import require_jetlink_stopped
    require_jetlink_stopped()
    base = base_url(a.route_url)
    opener = build_opener(NoRedirect())
    with opener.open(Request(base+'/manifest', headers={'Accept':'application/json'}), timeout=30) as response:
        raw = response.read(MAX_MANIFEST + 1)
    if len(raw) > MAX_MANIFEST:
        raise ValueError('Manifest too large')
    index, entries = choose(json.loads(raw), base)[0]
    a.output.mkdir(parents=True, exist_ok=False)
    for entry in entries:
        require_jetlink_stopped()
        print(f"下載片段 {index}: {entry['name']} ({entry['size']/1024**2:.1f} MiB)", file=sys.stderr, flush=True)
        download(opener, entry, a.output)
    print(f'已取得片段 {index}', file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'紀錄下載停止：{type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(1)
