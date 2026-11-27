"""Export original paired C4 recordings using pinned Tony geometry, measured motion only."""
import argparse
from bisect import bisect_right
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from replay import TONY_REV, OFFSETS_US, offline_guard, read_sample

VIDEO = {1:("wideRoadEncodeIdx","wideRoadCameraState","ecamera.hevc"),
         6:("roadEncodeIdx","roadCameraState","fcamera.hevc")}

def frame_table(index, camera):
    rows = [(sof,frame,eof,pos) for (frame,eof,sof),pos in index.items()
            if pos is not None and camera.get((frame,eof)) == sof]
    return sorted(rows)

def choose(rows, query):
    times = [r[0] for r in rows]
    result = []
    for offset in OFFSETS_US*1000:
        target = query+int(offset)
        i = bisect_right(times,min(query,target+10000000))-1
        if i < 0 or target-times[i]>150000000: return None
        result.append(rows[i])
    return result if len({r[1] for r in result})==5 else None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--segment",type=Path,required=True)
    p.add_argument("--tony-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--max-samples",type=int,default=6)
    a=p.parse_args()
    offline_guard()
    if not 1<=a.max_samples<=60: p.error("max-samples must be 1..60")
    root=a.tony_root.resolve()
    if subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()!=TONY_REV:
        raise ValueError("Use the pinned Tony checkout")
    if subprocess.check_output(["git","-C",str(root),"status","--porcelain","--untracked-files=no"],text=True).strip():
        raise ValueError("Tony checkout has tracked modifications")
    sys.path.insert(0,str(root))
    from openpilot.selfdrive.alpamayo.geometry import calibrated_image
    from openpilot.selfdrive.alpamayo.history import measured_history
    from openpilot.selfdrive.alpamayo.frontend import State, Unavailable
    from openpilot.selfdrive.alpamayo.capture import state_value
    import capnp
    import av
    import zstandard
    cereal=root/"openpilot/cereal"
    car=root/"opendbc_repo/opendbc/car"
    if not (car/"car.capnp").is_file(): raise ValueError("Pinned opendbc schema missing")
    capnp.remove_import_hook()
    log=capnp.load(str(cereal/"log.capnp"),imports=[str(cereal),str(cereal/"include"),str(car),str(car/"include")])
    segment=a.segment.resolve()
    for name in ("rlog.zst","fcamera.hevc","ecamera.hevc"):
        if not (segment/name).is_file(): raise ValueError("Missing "+name)
    segnum=int(segment.name.rsplit("--",1)[1])
    config=json.loads((root/"openpilot/selfdrive/alpamayo/release.json").read_text())["config"]
    with zstandard.open(segment/"rlog.zst","rb") as f: data=f.read((160<<20)+1)
    if len(data)>160<<20: raise ValueError("Log too large")
    indexes={k:{} for k in VIDEO}; cameras={k:{} for k in VIDEO}
    motion=[]; cal=[]; nav=[]; mici=False
    for event in log.Event.read_multiple_bytes(data):
        kind=event.which(); stamp=int(event.logMonoTime)
        if kind=="deviceState" and event.valid:
            mici |= str(event.deviceState.deviceType)=="mici"
        if kind in ("livePose","liveCalibration","navInstruction"):
            key={"livePose":"deviceMotion","liveCalibration":"extrinsicsCalibration","navInstruction":"navInstruction"}[kind]
            msg=getattr(event,kind); value,valid=state_value(key,msg)
            t=int(msg.timestamp) if kind=="livePose" else stamp
            if 0<t<=stamp:
                {"livePose":motion,"liveCalibration":cal,"navInstruction":nav}[kind].append(State(t,stamp,value,bool(valid and event.valid)))
        for cam,(idx_name,cam_name,_) in VIDEO.items():
            if kind==idx_name and event.valid:
                idx=getattr(event,kind)
                if idx.segmentNum!=segnum: continue
                key=(int(idx.frameId),int(idx.timestampEof),int(idx.timestampSof))
                if str(idx.type)!="fullHEVC" or not 0<key[2]<=key[1]: continue
                indexes[cam][key]=int(idx.segmentId) if key not in indexes[cam] else None
            if kind==cam_name and event.valid:
                cs=getattr(event,kind); key=(int(cs.frameId),int(cs.timestampEof))
                if str(cs.sensor)=="os04c10" and 0<cs.timestampSof<=cs.timestampEof:
                    cameras[cam][key]=int(cs.timestampSof) if key not in cameras[cam] else None
    if not mici: raise ValueError("Not a recorded C4 segment")
    for s in (motion,cal,nav): s.sort(key=lambda x:(x.stamp,x.received))
    for idx in indexes.values():
        positions=list(idx.values())
        if not positions or None in positions or sorted(positions)!=list(range(len(positions))):
            raise ValueError("Ambiguous or incomplete encoded indices")
    rows={k:frame_table(indexes[k],cameras[k]) for k in VIDEO}
    selected=[]; last=0
    def causal_cal(t,receipt):
        candidates=[x for x in cal if x.stamp<=t and x.received<=receipt]
        if not candidates or not candidates[-1].valid or t-candidates[-1].stamp>1000000000:
            raise ValueError("Missing calibrated exposure")
        return candidates[-1].value
    for anchor in rows[6]:
        query=anchor[0]
        if query-last<1000000000: continue
        groups={k:choose(rows[k],query) for k in VIDEO}
        if any(v is None for v in groups.values()): continue
        receipt=max(r[2] for group in groups.values() for r in group)
        try:
            current=causal_cal(query,receipt)
            xyz,rot,_=measured_history([x for x in motion if x.received<=receipt],query,current["rpyCalib"])
            calibrations=[causal_cal(r[0],receipt) for k in VIDEO for r in groups[k]]
        except (ValueError,Unavailable): continue
        # Future measured motion is scoring only and never passed to inference.
        ground=None
        try:
            end=query+1500000000
            g,gr,_=measured_history([x for x in motion if x.received<=end+100000000],end,current["rpyCalib"])
            ground=((g[0,5:]-g[0,4]) @ gr[0,4]).astype(np.float32)
        except (ValueError,Unavailable): pass
        # No invented guidance: preserve only fresh recorded maneuver text.
        ns=[x for x in nav if x.stamp<=query and x.received<=receipt]
        text=""
        if ns and ns[-1].valid and query-ns[-1].stamp<=2000000000:
            text=str(ns[-1].value.get("maneuverPrimaryText",""))[:512]
        selected.append((query,groups,calibrations,xyz,rot,text,ground));last=query
        if len(selected)>=a.max_samples: break
    if not selected: raise ValueError("No synchronized dual-camera windows with measured motion")
    pixels={}
    for cam,(_,_,filename) in VIDEO.items():
        wanted={r[3] for _,groups,*_ in selected for r in groups[cam]}
        count=0
        with av.open(str(segment/filename)) as video:
            for i,frame in enumerate(video.decode(video=0)):
                count=i+1
                if i in wanted:
                    if (frame.width,frame.height)!=(1344,760): raise ValueError("Unexpected camera dimensions")
                    pixels[cam,i]=frame.to_ndarray(format="rgb24").transpose(2,0,1)
        if count!=len(indexes[cam]) or not all((cam,i) in pixels for i in wanted):
            raise ValueError("Decoded frame count does not match recorded indices")
    a.output.mkdir(parents=True,exist_ok=False)
    for i,(query,groups,cals,xyz,rot,text,ground) in enumerate(selected):
        offline_guard()
        frames=[];timestamps=[]
        for cam in VIDEO:
            for r in groups[cam]:
                frames.append(calibrated_image(pixels[cam,r[3]],cam,config["geometry"],cals[len(frames)]))
                timestamps.append(r[0]//1000)
        out=a.output/f"{i:03d}.npz"
        kwargs=dict(image_frames=np.stack(frames),camera_indices=np.array([1]*5+[6]*5),
            absolute_timestamps=np.array(timestamps,dtype=np.int64),ego_history_xyz=xyz,ego_history_rot=rot,
            query_us=np.int64(query//1000),nav_text=np.array(text),source_revision=np.array(TONY_REV))
        if ground is not None: kwargs["ground_xyz"]=ground
        np.savez_compressed(out,**kwargs);read_sample(out)
        print("Exported",out.name,flush=True)

if __name__=="__main__": main()
