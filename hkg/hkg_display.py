"""Local HKG display preferences and a macOS native settings dialog."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time

SETTINGS = Path.home() / 'Library/Application Support/CarrotMacHUD/hkg-display.json'
DEFAULTS = {'orientation': 0, 'brightness': 75}
PARAMS = {'ClusterHudOrientation': 'orientation', 'ClusterHudBrightness': 'brightness'}


def validate(value):
  if not isinstance(value, dict) or set(value) - set(DEFAULTS):
    raise ValueError('無效的 HUD 顯示設定')
  result = {**DEFAULTS, **value}
  if type(result['orientation']) is not int or result['orientation'] not in (0, 2):
    raise ValueError('方向只能是正常或旋轉 180°')
  if type(result['brightness']) is not int or not 1 <= result['brightness'] <= 100:
    raise ValueError('亮度必須介於 1–100')
  return result


def read_settings(path=SETTINGS):
  try:
    return validate(json.loads(path.read_text()))
  except FileNotFoundError:
    return dict(DEFAULTS)


def save_settings(value, path=SETTINGS):
  value = validate(value)
  path.parent.mkdir(parents=True, exist_ok=True)
  fd, pending = tempfile.mkstemp(prefix='.hkg-display-', dir=path.parent)
  try:
    with os.fdopen(fd, 'w') as stream:
      json.dump(value, stream)
      stream.write('\n')
    os.replace(pending, path)
  finally:
    Path(pending).unlink(missing_ok=True)


class DisplaySettings:
  def __init__(self, path=SETTINGS):
    self.path = path
    self.values = dict(DEFAULTS)
    self.next_read = 0.

  def get(self, key):
    if key not in PARAMS:
      return None
    now = time.monotonic()
    if now >= self.next_read:
      try:
        self.values = read_settings(self.path)
      except (OSError, ValueError):
        # A damaged preference must not repeatedly reset the display.
        pass
      self.next_read = now + .5
    return str(self.values[PARAMS[key]]).encode()


def diagnostics():
  directory = Path(os.environ.get('CARROT_HUD_DIR', str(Path.home() / 'Library/Caches/io.zoompilot.jetlink/carrot-hud')))
  lines = []
  for name, binary in (('snapshot.packet', True), ('status.json', False)):
    try:
      path = directory / name
      if binary:
        with path.open('rb') as stream:
          stamp, = struct.unpack('<d', stream.read(8))
          data = json.loads(stream.read(512 * 1024 + 1))
        lines.append(f"接收封包距今 {time.time() - stamp:.2f} 秒；來源 {data.get('source', 'Carrot/未標記')}")
        lines.append('車況來源：' + ', '.join(data.get('hkg', {})))
      else:
        data = json.loads(path.read_text())
        lines.append(f"螢幕輸出 heartbeat 距今 {time.time() - float(data['updated_epoch']):.2f} 秒")
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
      lines.append(f'{name}：無法讀取（{error}）')
  log = Path.home() / 'Library/Logs/CarrotMacHUD/hud.log'
  lines.append('\n最近 HUD 日誌（可貼給協助排查的人）：')
  try:
    with log.open('rb') as stream:
      stream.seek(0, 2)
      stream.seek(max(0, stream.tell() - 12000))
      lines.extend(stream.read().decode(errors='replace').splitlines()[-45:])
  except OSError as error:
    lines.append(str(error))
  return '\n'.join(lines)


def choose(prompt, options):
  script = '''on run argv
    set choices to items 2 thru -1 of argv
    set resultList to choose from list choices with title "HKG HUD 顯示設定" with prompt (item 1 of argv)
    if resultList is false then return ""
    return item 1 of resultList
  end run'''
  return subprocess.check_output(['osascript', '-e', script, prompt, *options], text=True).strip()


def message(text):
  subprocess.run(['osascript', '-e', '''on run argv
    display dialog (item 1 of argv) with title "HKG HUD 顯示設定" buttons {"好"} default button "好"
  end run''', text], check=True)


def main():
  if '--diagnose' in sys.argv:
    print(diagnostics())
    return
  if sys.platform != 'darwin':
    raise ValueError('請在 Mac 執行設定視窗')
  helper = Path.home() / 'CarrotMacHUD/carrot/tools/jetlink'
  if not (helper / 'hkg_display.py').is_file():
    message('請先安裝新版 06-HKG-HUD.command，再開啟設定。')
    return
  while True:
    value = read_settings()
    direction = '正常' if value['orientation'] == 0 else '旋轉 180°'
    action = choose(f"目前：{direction}，亮度 {value['brightness']}%。設定僅套用 HKG HUD。",
                    ['畫面方向', '亮度', '查看並複製閃爍診斷', '結束'])
    if not action or action == '結束':
      return
    if action == '畫面方向':
      selected = choose('上下顛倒請選旋轉 180°；HUD 會短暫重開顯示，C4 不需重啟。', ['正常', '旋轉 180°'])
      if selected:
        value['orientation'] = 0 if selected == '正常' else 2
        save_settings(value)
    elif action == '亮度':
      selected = choose('亮度會在 HUD 執行時套用。', [f'{n}%' for n in (10, 25, 50, 75, 100)])
      if selected:
        value['brightness'] = int(selected[:-1])
        save_settings(value)
    elif action == '查看並複製閃爍診斷':
      text = diagnostics()
      print(text, flush=True)
      subprocess.run(['pbcopy'], input=text, text=True, check=True)
      message('診斷已複製，可直接貼到對話中。\n\n' + text[:1200])


if __name__ == '__main__':
  try:
    main()
  except (OSError, ValueError, subprocess.CalledProcessError) as error:
    print('HUD 設定停止：' + str(error), file=sys.stderr)
    sys.exit(1)
