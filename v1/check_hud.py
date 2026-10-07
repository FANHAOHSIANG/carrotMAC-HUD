"""Five-second receiver health check; reads only the local HUD IPC files."""
import json
from pathlib import Path
import struct
import time

root = Path.home() / 'Library/Caches/io.zoompilot.jetlink/carrot-hud'
for _ in range(5):
    try:
        raw = (root / 'snapshot.packet').read_bytes()
        stamp, = struct.unpack_from('<d', raw)
        record = json.loads(raw[8:])
        age = time.time() - stamp
        print(f'HUD snapshot age={age:.3f}s, bytes={len(raw)}, version={record.get("version")}, '
              f'host={record.get("external_compute_label")}, events={len(record.get("events", {}))}')
        if not 0 <= age < .5:
            print('封包已過期：請检查 C4 和修改版 JetLink 的連線。')
        status = json.loads((root / 'status.json').read_text())
        print('TURZX output heartbeat:', status.get('connected'),
              'age:', round(time.time() - status['updated_epoch'], 2), 's')
    except (OSError, ValueError, struct.error, KeyError) as exc:
        print('尚未收到封包或尚未輸出畫面：', exc)
    time.sleep(1)
