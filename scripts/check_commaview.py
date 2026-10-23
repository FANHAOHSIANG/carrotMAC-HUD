"""Read-only preflight for a future Jetlink-owned CommaView display receiver.

Does not pair, read credentials, start a renderer, open USB, or change C4 files.
The official v0.0.59-beta installer uses GET /commaview/version on port 5002.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'AppAutostart'))
from mac_hud_supervisor import packet_kind


def version_url(host):
  address = ipaddress.ip_address(host.strip())
  if address.is_unspecified or address.is_multicast:
    raise ValueError('請輸入 C4 的 IP 位址')
  literal = '[' + str(address) + ']' if address.version == 6 else str(address)
  return 'http://' + literal + ':5002/commaview/version'


class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    return None


def check_version(host):
  # Bypass system HTTP proxies for this explicit device connection. Never send
  # a token, follow redirects, or print arbitrary server content in diagnostics.
  url = version_url(host)
  opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
  request = urllib.request.Request(url, headers={'Accept': 'application/json'}, method='GET')
  try:
    with opener.open(request, timeout=3) as response:
      raw = response.read(32769)
    if len(raw) > 32768:
      return 'CommaView 版本 API：回覆超過大小限制'
    value = json.loads(raw)
    if not isinstance(value, dict):
      return 'CommaView 版本 API：回覆格式不符'
    versions = []
    for key in ('version', 'runtimeVersion', 'runtimeTag', 'releaseTag'):
      item = value.get(key)
      if isinstance(item, str) and re.fullmatch(r'v?\d+\.\d+\.\d+(?:[-+.][A-Za-z0-9.-]+)?', item):
        versions.append(key + '=' + item)
    return 'CommaView 版本 API：收到 JSON 回覆；' + (', '.join(versions) or '未識別版本欄位')
  except urllib.error.HTTPError as error:
    return f'CommaView 版本 API：HTTP {error.code}（未嘗試配對或認證）'
  except (OSError, ValueError):
    return 'CommaView 版本 API：無法讀取；請確認 C4 IP、同一網路及服務狀態'


def local_status(base, directory, duration=3.):
  lines = []
  app = base / 'jetlink/macos/build/Jetlink.app/Contents/MacOS/Jetlink'
  try:
    sys.path.insert(0, str(ROOT / 'scripts'))
    from enable_hkg import check_app
    lines.append('Jetlink App HUD 入口：' + check_app(app.read_bytes()))
  except (OSError, ValueError):
    lines.append('Jetlink App HUD 入口：未確認（找不到檔案或缺少標記）')
  stamps, kinds = set(), set()
  deadline = time.monotonic() + duration
  while time.monotonic() < deadline:
    observed = packet_kind(directory / 'snapshot.packet')
    if observed:
      kind, stamp = observed
      kinds.add(kind)
      stamps.add(stamp)
    time.sleep(.1)
  lines.append(f'{duration:g} 秒內新鮮 HUD 封包：{len(stamps)}；來源：' + (', '.join(sorted(kinds)) or '未收到'))
  try:
    with (directory / 'status.json').open('rb') as stream:
      value = json.loads(stream.read(32769))
    age = time.time() - float(value['updated_epoch'])
    if not 0 <= age <= 86400:
      raise ValueError('invalid heartbeat age')
    lines.append(f'HUD 輸出 heartbeat 距今：{age:.2f} 秒')
  except (OSError, ValueError, TypeError, KeyError):
    lines.append('HUD 輸出 heartbeat：未確認')
  return lines


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--host', help='C4 IP address, not a URL or pair code')
  parser.add_argument('--base', type=Path, default=Path.home() / 'CarrotMacHUD')
  args = parser.parse_args()
  if not args.host:
    if sys.platform != 'darwin':
      parser.error('請使用 --host 輸入 C4 IP')
    prompt = 'text returned of (display dialog "輸入 C4 的 Wi-Fi IP（C4 設定 → 網路）。只檢查服務，不會安裝或配對。" default answer "" with title "Jetlink / CommaView 檢查")'
    result = subprocess.run(['osascript', '-e', prompt], capture_output=True, text=True)
    if result.returncode:
      return
    args.host = result.stdout.strip()
  directory = Path.home() / 'Library/Caches/io.zoompilot.jetlink/carrot-hud'
  lines = ['Jetlink / CommaView 整合前檢查（不是影像接收器）', check_version(args.host)]
  lines.extend(local_status(args.base, directory))
  lines.append('CommaView 配對、影像解碼及 HUD 合成：尚未實作，API 可達不代表影像可用。')
  report = '\n'.join(lines)
  print(report, flush=True)
  if sys.platform == 'darwin':
    copied = subprocess.run(['pbcopy'], input=report, text=True).returncode == 0
    message = '檢查完成，結果已複製。請回到對話貼上。' if copied else '檢查完成，請複製終端機結果貼回對話。'
    subprocess.run(['osascript', '-e', 'on run argv\ndisplay dialog (item 1 of argv) buttons {"好"} default button "好"\nend run', message], check=True)


if __name__ == '__main__':
  try:
    main()
  except (OSError, ValueError) as error:
    print('檢查停止：' + str(error), file=sys.stderr)
    raise SystemExit(1)
