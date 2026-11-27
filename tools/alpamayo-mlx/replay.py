"""Recorded-only Alpamayo 2 Edge MLX benchmark. No vehicle or JetLink interface."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time
import numpy as np

MODEL = "Safman/Alpamayo2-Edge-MLX-q4"
MLX_REV = "43893667449fd5cdc621a8c8da3624ce014f202f"
TONY_REV = "980a186d4b63d6f0a62ab2b487dbdfe3f2939127"
OFFSETS_US = np.array([-2000000, -1000000, -500000, -100000, 0])
FIELDS = {"image_frames", "camera_indices", "absolute_timestamps", "ego_history_xyz",
          "ego_history_rot", "query_us", "nav_text", "source_revision"}

def offline_guard():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Apple Silicon macOS required for inference")
    for name in ("Jetlink", "CarrotMacHUD"):
        if subprocess.run(["/usr/bin/pgrep", "-ix", name], stdout=subprocess.DEVNULL).returncode != 1:
            raise RuntimeError("Quit Jetlink and HUD, disconnect C4 before replay")

def read_sample(path):
    if path.stat().st_size > 40 * 1024 * 1024:
        raise ValueError("Oversized NPZ")
    with np.load(path, allow_pickle=False) as src:
        if not FIELDS <= set(src.files):
            raise ValueError("Incomplete recorded sample")
        a = {k: src[k] for k in FIELDS}
        ground = src["ground_xyz"] if "ground_xyz" in src.files else None
    frames, cams, ts = (a[k] for k in ("image_frames","camera_indices","absolute_timestamps"))
    if frames.shape == (10,1,3,432,768):
        frames = frames[:,0]
    if frames.shape != (10,3,432,768) or frames.dtype != np.uint8:
        raise ValueError("Require ten calibrated RGB frames, not qcamera")
    if cams.dtype.kind not in "iu" or cams.shape != (10,) or not np.array_equal(cams, [1]*5+[6]*5):
        raise ValueError("Require camera IDs 1 and 6, five frames each")
    if a["query_us"].shape != () or a["query_us"].dtype.kind not in "iu":
        raise ValueError("Invalid query timestamp")
    query = int(a["query_us"])
    if query <= 2000000 or ts.dtype.kind not in "iu" or ts.shape != (10,):
        raise ValueError("Invalid exposure timestamps")
    ts = ts.astype(np.int64)
    for group in (ts[:5], ts[5:]):
        delta = group - query - OFFSETS_US
        if (group <= 0).any() or (np.diff(group) <= 0).any() or (group > query).any() or (delta < -150000).any() or (delta > 10000).any():
            raise ValueError("Noncausal, repeated or stale exposure")
    if ts[-1] != query:
        raise ValueError("Telephoto query must be the recorded anchor")
    xyz, rot = a["ego_history_xyz"], a["ego_history_rot"]
    if xyz.shape == (1,20,3): xyz = xyz[None]
    if rot.shape == (1,20,3,3): rot = rot[None]
    if xyz.shape != (1,1,20,3) or rot.shape != (1,1,20,3,3) or xyz.dtype.kind != "f" or rot.dtype.kind != "f":
        raise ValueError("Require twenty measured poses")
    if not np.isfinite(xyz).all() or not np.isfinite(rot).all() or not np.allclose(xyz[0,0,-1],0,atol=.01):
        raise ValueError("Invalid ego history")
    if not np.allclose(rot @ rot.swapaxes(-1,-2), np.eye(3), atol=.005) or not np.allclose(np.linalg.det(rot),1,atol=.005) or not np.allclose(rot[0,0,-1],np.eye(3),atol=.005):
        raise ValueError("Invalid rotation history")
    for key in ("nav_text","source_revision"):
        if a[key].shape != () or a[key].dtype.kind != "U":
            raise ValueError("Invalid sample metadata")
    if str(a["source_revision"]) != TONY_REV or len(str(a["nav_text"])) > 512:
        raise ValueError("Unrecognized export source or navigation")
    if ground is not None and (ground.shape != (15,3) or ground.dtype.kind != "f" or not np.isfinite(ground).all()):
        raise ValueError("Invalid reference trajectory")
    return dict(image_frames=frames, camera_indices=cams, absolute_timestamps=ts,
                ego_history_xyz=xyz.astype(np.float32), ego_history_rot=rot.astype(np.float32)), query, str(a["nav_text"]), ground

def result_xyz(pred):
    xyz = np.asarray(pred)
    if xyz.shape != (1,1,1,64,3) or not np.isfinite(xyz).all():
        raise ValueError("Expected finite 64-waypoint trajectory")
    return xyz[0,0,0]

def score(xyz, ground):
    if ground is None: return None
    err = xyz[:15] - ground
    return dict(ade_1_5s_m=float(np.linalg.norm(err[:,:2],axis=1).mean()),
                max_forward_m=float(np.abs(err[:,0]).max()),
                max_lateral_m=float(np.abs(err[:,1]).max()))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--revision", help="Hugging Face exact commit; first run resolves and records current SHA")
    p.add_argument("--max-samples", type=int, default=6)
    p.add_argument("--offline-bench", action="store_true", required=True)
    a = p.parse_args()
    offline_guard()
    if not 1 <= a.max_samples <= 60: p.error("max-samples must be 1..60")
    paths = sorted(a.samples.glob("*.npz"))[:a.max_samples]
    if not paths: p.error("No exported NPZ samples")
    for path in paths: read_sample(path)
    from huggingface_hub import HfApi, snapshot_download
    from mlx_vlm import load
    import mlx.core as mx
    if not mx.metal.is_available(): raise RuntimeError("Metal unavailable")
    mx.set_default_device(mx.gpu)
    revision = a.revision or HfApi().model_info(MODEL).sha
    if not re.fullmatch(r"[0-9a-f]{40}", revision): raise ValueError("Expected exact weight revision")
    weights = snapshot_download(MODEL, revision=revision, allow_patterns=["*.json","*.safetensors","*.jinja","*.txt","*.model"])
    offline_guard()
    a.output.mkdir(parents=True, exist_ok=False)
    t = time.perf_counter()
    model, processor = load(weights)
    mx.synchronize()
    load_ms = (time.perf_counter()-t)*1000
    if not hasattr(model,"prepare_driving_inputs") or not hasattr(model,"sample_trajectories"):
        raise RuntimeError("Incompatible MLX-VLA model")
    metrics = []
    with (a.output/"results.jsonl").open("x",encoding="utf-8") as f:
        for path in paths:
            offline_guard()
            sample, query, nav, ground = read_sample(path)
            mx.reset_peak_memory()
            start = time.perf_counter()
            # No pruning, nominal fast path, or altered diffusion in baseline.
            inputs = model.prepare_driving_inputs(sample,processor,nav_text=nav,use_vision_cache=True)
            pred, rotations, _, extra = model.sample_trajectories(inputs,tokenizer=processor.tokenizer,
                num_traj_sets=1,num_traj_samples=1,reasoning_mode="adaptive",temperature=.6,
                diffusion_steps=10,seed=42)
            mx.synchronize()
            xyz = result_xyz(pred)
            elapsed = (time.perf_counter()-start)*1000
            record = dict(sample=path.name,query_us=query,model=MODEL,revision=revision,mlx_source=MLX_REV,
                source_revision=TONY_REV,mode="offline_public_q4_baseline",navigation=nav,
                trajectory_xyz=xyz.tolist(),reasoning=str(extra["cot"][0,0,0]),
                inference_ms=round(elapsed,2),peak_metal_bytes=mx.get_peak_memory(),
                measured_reference=score(xyz,ground))
            f.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+"\n"); f.flush()
            metrics.append(elapsed)
            print(path.name, round(elapsed,2),"ms",flush=True)
    summary = dict(model=MODEL,revision=revision,mlx_source=MLX_REV,samples=len(metrics),
        load_ms=round(load_ms,2),p50_ms=float(np.percentile(metrics,50)),p95_ms=float(np.percentile(metrics,95)),
        sequential_hz=1000/float(np.mean(metrics)),device=platform.machine(),offline_only=True)
    (a.output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))

if __name__ == "__main__":
    main()
