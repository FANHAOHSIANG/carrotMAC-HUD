"""Lab-only VLA observer over Jetlink's existing read-only snapshot.

Never sends vehicle commands or replaces primary inference. Do not run on a
moving vehicle: this experimental shared-resource path is not qualified.
"""
import argparse
import base64
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import signal
import time

from jetlink_input import DEFAULT, Feed, TTL_NS, compare, load_schema, read_packet
from replay import decode, reference, resize_road, verify


def worker(requests, replies, weights, server, device):
    # Own the model server and only its process group. The supervisor may stop
    # this entire group without touching the independent Jetlink process.
    os.setsid()
    os.nice(10)
    import cv2
    import numpy as np
    try:
        verify(weights)
        with reference(weights, server, device) as (backend, predict):
            replies.put(('ready', backend))
            while True:
                sample = requests.get()
                if sample is None:
                    return
                raw = base64.b64decode(sample['jpeg'], validate=True)
                if len(raw) > 512 * 1024:
                    raise ValueError('oversized preview')
                bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                if bgr is None:
                    raise ValueError('invalid ROAD preview')
                rgb = resize_road(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                action = decode(predict(rgb, sample['egomotion']))
                replies.put(('result', (sample['frame_id'], sample['timestamp_eof_ns'], action)))
    except Exception as exc:
        replies.put(('error', type(exc).__name__))


def stop_worker(proc):
    if proc.pid is None:
        return
    # Worker group is separate from Jetlink. Check it is the expected group
    # before sending a group signal, including failure during startup.
    try:
        if os.getpgid(proc.pid) == proc.pid:
            os.killpg(proc.pid, signal.SIGTERM)
        elif proc.is_alive():
            proc.terminate()
    except ProcessLookupError:
        pass
    proc.join(2)
    if proc.is_alive():
        try:
            if os.getpgid(proc.pid) == proc.pid:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        proc.join(2)
    # The child group may still contain llama-server after the leader exits.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def emit(state, **fields):
    print(json.dumps({'state':state, **fields}), flush=True)


def observe(args):
    feed = Feed(load_schema(args.schema_root))
    ctx = mp.get_context('spawn')
    requests, replies = ctx.Queue(1), ctx.Queue(2)
    requests.cancel_join_thread()
    replies.cancel_join_thread()
    proc = None
    eligible = None
    pending = None
    deadline = None
    last_stamp = None
    last_received = None
    last_submit = 0.
    ready = False
    misses = accepted = 0
    first = True
    until = time.monotonic() + args.seconds
    emit('waiting', mode='lab-only')
    try:
        while time.monotonic() < until:
            now = time.monotonic()
            sample = None
            try:
                stamp, obj = read_packet(args.snapshot)
                if stamp != last_stamp:
                    last_stamp = stamp
                    last_received = now
                    sample = feed.ingest(obj)
            except (OSError, ValueError, KeyError, TypeError):
                feed.reset()
            good = feed.good and last_received is not None and now-last_received < .25
            if not good:
                eligible = None
                if proc is not None:
                    emit('primary_guard')
                    break
            elif eligible is None:
                eligible = now
            elif proc is None and now-eligible >= 2:
                proc = ctx.Process(target=worker,args=(requests,replies,args.weights,args.server,args.device))
                proc.start()
                deadline = now + 120
                emit('loading')
            if proc is not None:
                if not proc.is_alive() or (deadline is not None and now > deadline):
                    emit('worker_failed')
                    break
                try:
                    kind, value = replies.get_nowait()
                except queue.Empty:
                    kind = None
                if kind == 'ready' and not ready:
                    ready = True
                    deadline = None
                    emit('ready', backend=value)
                elif kind == 'result' and pending is not None:
                    frame, eof, action = value
                    s, dispatched, initial_age = pending
                    age = initial_age + int((time.monotonic()-dispatched)*1e9)
                    match = (frame,eof) == (s['frame_id'],s['timestamp_eof_ns'])
                    if match and 0 <= age < TTL_NS:
                        misses = 0
                        accepted += 1
                        emit('result',frame_id=frame, estimated_age_ms=age/1e6,
                             comparison=compare(s['primary'],action),primary=s['primary'],action=action)
                    else:
                        misses += 1
                        emit('expired', consecutive=misses)
                    pending = None
                    deadline = None
                    if misses >= 3:
                        emit('too_slow')
                        break
                elif kind is not None:
                    emit('worker_failed',reason='unexpected_worker_reply')
                    break
                if ready and pending is None and sample is not None and now-last_submit >= .5:
                    # C4 exposure-to-send age + Mac receipt-to-submit age.
                    # Transport delay is unknown; never label this end-to-end latency.
                    initial_age = sample['source_age_ns'] + int(max(0,time.time()-stamp)*1e9)
                    if initial_age < 150_000_000:
                        requests.put_nowait(sample)
                        pending = (sample,time.monotonic(),initial_age)
                        deadline = now + (45 if first else 12)
                        first = False
                        last_submit = now
                        emit('inferencing',frame_id=sample['frame_id'])
            time.sleep(.025)
    finally:
        if proc is not None:
            stop_worker(proc)
        requests.close()
        replies.close()
        emit('stopped', accepted=accepted,consecutive_expired=misses)


def main():
    import platform
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lab-only', action='store_true',required=True,help='Confirm isolated bench/replay, not a moving vehicle')
    p.add_argument('--schema-root',type=Path,required=True)
    p.add_argument('--snapshot',type=Path,default=DEFAULT)
    p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--server',type=Path,required=True)
    p.add_argument('--device')
    p.add_argument('--seconds',type=float,default=120)
    a=p.parse_args()
    if platform.system()!='Darwin' or platform.machine()!='arm64':
        p.error('Apple Silicon macOS required')
    if not 0<a.seconds<=600:
        p.error('duration must be 0–600 seconds')
    if not a.server.is_file() or not os.access(a.server,os.X_OK):
        p.error('verified Metal llama-server required; prepare weights offline first')
    observe(a)

if __name__=='__main__':
    main()
