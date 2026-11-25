"""Read-only Jetlink HUD snapshot input for experimental Mac VLA.

No vehicle commands, USB ownership, model selection or writes to Jetlink.
The snapshot is a lossy display feed: unmatched/stale inputs are rejected.
"""
import argparse
import base64
from collections import deque
import json
import math
import os
from pathlib import Path
import struct
import time

from jetlink_motion import MotionWindow, primary_action

MAX_PACKET = 512 * 1024
INPUT_NS = 150_000_000
TTL_NS = 500_000_000
DEFAULT = Path.home() / 'Library/Caches/io.zoompilot.jetlink/carrot-hud/snapshot.packet'
REQUIRED = ('modelV2', 'carState', 'livePose', 'liveCalibration', 'deviceState')

def read_packet(path, wall=None):
    wall = time.time() if wall is None else wall
    with path.open('rb') as f:
        raw = f.read(MAX_PACKET + 9)
    if not 8 < len(raw) <= MAX_PACKET + 8:
        raise ValueError('bad snapshot length')
    stamp, = struct.unpack_from('<d', raw)
    if not 0 <= wall-stamp < .5:
        raise ValueError('stale snapshot')
    obj = json.loads(raw[8:])
    if obj.get('version') != 1 or not math.isfinite(obj['sent']):
        raise ValueError('unsupported snapshot')
    for key in ('events', 'valid', 'alive', 'cameras'):
        if not isinstance(obj.get(key), dict):
            raise ValueError('missing snapshot section')
    return stamp, obj

def load_schema(root):
    import capnp
    cereal = root / 'openpilot/cereal'
    car = root / 'opendbc_repo/opendbc/car'
    capnp.remove_import_hook()
    return capnp.load(str(cereal/'log.capnp'), imports=[str(cereal),str(cereal/'include'),str(car),str(car/'include')])

def healthy(model, source_ns, device, label):
    return (label == 'MAC' and model.visionCompute in ('nonUsb', 'usbGpu') and
            primary_action(model) is not None and 0 <= source_ns-model.timestampEof < INPUT_NS and
            model.frameAge == 0 and 0 <= model.frameDropPerc < 1 and
            0 < model.modelExecutionTime < .05 and device.thermalStatus == 'green' and
            0 < device.memoryUsagePercent < 85)

def compare(primary, action):
    stop = action.get('longitudinal')
    if stop is None:
        return 'unknown'
    a, b = bool(primary['should_stop']), stop == 'stop'
    return 'both_stop' if a and b else 'primary_only_stop' if a else 'vla_only_stop' if b else 'neither_stop'

class Feed:
    def __init__(self, schema):
        self.schema = schema
        self.reset()

    def reset(self):
        self.motion = MotionWindow()
        self.events = {}
        self.images = deque(maxlen=5)
        self.primaries = deque(maxlen=5)
        self.last_source = -1
        self.last_pair = (-1, -1)
        self.good = False

    def ingest(self, obj):
        from contextlib import ExitStack
        self.good = False
        source = round(obj['sent'] * 1e9)
        if source < self.last_source:
            self.reset()
        if source == self.last_source:
            return None
        self.last_source = source
        if not all(obj['valid'].get(k) is True and obj['alive'].get(k) is True for k in REQUIRED):
            self.reset()
            return None
        with ExitStack() as stack:
            decoded = {}
            for k in REQUIRED:
                raw = base64.b64decode(obj['events'][k], validate=True)
                e = stack.enter_context(self.schema.Event.from_bytes(raw))
                if not e.valid or e.which() != k:
                    self.reset()
                    return None
                decoded[k] = e
            model, device = decoded['modelV2'].modelV2, decoded['deviceState'].deviceState
            if not healthy(model, source, device, obj.get('external_compute_label')):
                self.reset()
                return None
            self.good = True
            updates = sorted((int(decoded[k].logMonoTime),k) for k in ('carState','livePose','liveCalibration'))
            for t,k in updates:
                if t <= self.events.get(k,-1):
                    continue
                self.events[k] = t
                self.motion.observe(k,t,True,getattr(decoded[k],k))
            self.motion.trim(source-2_600_000_000)
            key = (int(model.frameId), int(model.timestampEof))
            if not self.primaries or key != self.primaries[-1][0]:
                self.primaries.append((key,primary_action(model)))
        cam = obj['cameras'].get('road_hd') or obj['cameras'].get('road')
        if cam:
            k = (int(cam['frame']),round(float(cam['capture_time'])*1e9))
            if 0 <= source-k[1] < INPUT_NS and (not self.images or k != self.images[-1][0]):
                self.images.append((k,cam['jpeg']))
        by_key = dict(self.primaries)
        for key,jpeg in reversed(self.images):
            if key not in by_key or key[0] <= self.last_pair[0] or key[1] <= self.last_pair[1] or not 0 <= source-key[1] < INPUT_NS:
                continue
            history = self.motion.at(key[1])
            if history is None:
                continue
            self.last_pair = key
            return {'frame_id':key[0],'timestamp_eof_ns':key[1],'source_age_ns':source-key[1],
                    'egomotion':history,'primary':by_key[key],'jpeg':jpeg}
        return None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema-root',type=Path,required=True,help='Exact checked-out fusion schema')
    p.add_argument('--snapshot',type=Path,default=DEFAULT)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--capture-only',action='store_true',required=True)
    a=p.parse_args()
    if not 0 < a.seconds <= 600:
        p.error('duration must be 0–600 seconds')
    feed=Feed(load_schema(a.schema_root))
    until=time.monotonic()+a.seconds
    last_stamp=None
    count=0
    while time.monotonic()<until:
        try:
            stamp,obj=read_packet(a.snapshot)
            if stamp != last_stamp:
                last_stamp=stamp
                sample=feed.ingest(obj)
                if sample:
                    count+=1
                    print(json.dumps({k:v for k,v in sample.items() if k!='jpeg'}),flush=True)
        except (OSError,ValueError,KeyError,TypeError):
            feed.reset()
        time.sleep(.025)
    print(json.dumps({'matched':count,'mode':'capture-only','gpu_inference':False}),flush=True)

if __name__=='__main__':
    main()
