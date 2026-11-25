"""Independent offline VLA supervisor. No vehicle or Jetlink writes."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path.home() / 'Library/Application Support/CarrotMacHUD/VLA-Offline/standalone'
SCRIPT = Path(__file__).resolve().with_name('Run-VLA-Offline.command')

def prepare():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROOT.chmod(0o700)

def state():
    try:
        obj = json.loads((ROOT/'active.json').read_text())
        if not isinstance(obj.get('run'), str) or len(obj['run']) != 32 or not all(c in '0123456789abcdef' for c in obj['run']):
            return None
        return obj
    except (OSError, ValueError):
        return None

def jetlink_stopped():
    return subprocess.run(['/usr/bin/pgrep','-x','Jetlink'], stdout=subprocess.DEVNULL).returncode == 1

def terminate_group(child):
    # Only signal the dedicated process group created by this supervisor.
    for sig, duration in ((signal.SIGINT,3),(signal.SIGTERM,3),(signal.SIGKILL,1)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            break
        until = time.monotonic() + duration
        while time.monotonic() < until:
            child.poll()
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.1)
    child.wait(timeout=2)

def start(route):
    with (ROOT/'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('VLA 已在執行；請先停止')
        if not jetlink_stopped():
            raise RuntimeError('請先退出正式版 Jetlink')
        print('請停車、退出 HUD、拔除 C4 USB。VLA 只分析既有紀錄，不接收行車即時資料。')
        if input('確認後輸入 YES：').strip() != 'YES':
            return
        if not jetlink_stopped():
            raise RuntimeError('Jetlink 尚未退出')
        token = uuid.uuid4().hex
        log_path = ROOT / (token+'.log')
        stop_file = ROOT / (token+'.stop')
        active = ROOT/'active.json'
        tmp = ROOT/(token+'.json')
        tmp.write_text(json.dumps({'run': token, 'log': str(log_path)}))
        tmp.replace(active)
        child = None
        stopping = False
        def stop_signal(*_):
            nonlocal stopping
            stopping = True
        previous = {sig:signal.signal(sig,stop_signal) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
        try:
            env = dict(os.environ, CARROT_VLA_SUPERVISED='1')
            args = ['/bin/bash',str(SCRIPT)] + ([route] if route else [])
            with log_path.open('x') as log:
                child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         env=env,start_new_session=True)
                print('VLA 已啟動。可另開終端機執行 Stop-VLA.command。')
                print('日誌：',log_path,flush=True)
                with log_path.open() as reader:
                    while child.poll() is None:
                        print(reader.read(),end='',flush=True)
                        if stopping or stop_file.exists() or not jetlink_stopped():
                            print('\n停止 VLA（手動要求或 Jetlink 已啟動）',flush=True)
                            terminate_group(child)
                            break
                        time.sleep(.5)
                    print(reader.read(),end='',flush=True)
                rc=child.wait()
                print('VLA 已退出，代碼：',rc)
                return rc
        finally:
            if child is not None:
                # Cover abnormal exits too; never touch the installed Jetlink process.
                terminate_group(child)
            active.unlink(missing_ok=True)
            stop_file.unlink(missing_ok=True)
            for sig,handler in previous.items():
                signal.signal(sig,handler)

def status(stop=False):
    with (ROOT/'lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            obj=state()
            if not obj:
                print('VLA 正在準備或結束，尚無可停止的工作；稍後再查。')
                return 1
            if not stop:
                print('VLA 工作進行中；日誌：',obj['log'])
                return 0
            (ROOT/(obj['run']+'.stop')).touch()
            print('已要求停止 VLA。')
            until=time.monotonic()+12
            while time.monotonic()<until:
                try:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    print('VLA 工作已停止。')
                    return 0
                except BlockingIOError:
                    time.sleep(.2)
            print('尚未確認停止；請檢查原啟動視窗。')
            return 1
        else:
            print('VLA 未執行。')
            return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('start','stop','status'))
    p.add_argument('route',nargs='?')
    a=p.parse_args()
    if sys.platform!='darwin':
        p.error('macOS only')
    prepare()
    if a.action=='start':
        return start(a.route)
    return status(a.action=='stop')

if __name__=='__main__':
    try:
        sys.exit(main() or 0)
    except (OSError,RuntimeError,ValueError) as e:
        print('VLA：',e,file=sys.stderr)
        sys.exit(1)
