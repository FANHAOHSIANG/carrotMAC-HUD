"""Mac front-camera recognition worker. All coordinates are image-relative."""
import argparse
import base64
import json
import os
import struct
import time
from pathlib import Path

CACHE = Path(os.environ.get("CARROT_HUD_DIR", Path.home() / "Library/Caches/io.zoompilot.jetlink/carrot-hud"))
KINDS = {"person", "motorcycle", "bicycle", "car", "truck", "bus"}


def packet_frame(data, wall_now):
    received, = struct.unpack_from("<d", data)
    packet = json.loads(data[8:])
    frame = packet["cameras"]["road"]
    age = packet["sent"] - frame.get("capture_time", frame["time"])
    # Both Python processes share Unix time, even with different macOS runtimes.
    receipt_age = wall_now - received
    if not (0 <= receipt_age < .5 and 0 <= age < .4):
        return None
    return (frame["frame"], frame["time"]), received - age, base64.b64decode(frame["jpeg"], validate=True)


def detect(model, image, cone=False):
    if cone:
        import cv2
        image = cv2.resize(image, (640, 640))
    result = model.predict(image, device="cpu", verbose=False, imgsz=640, conf=.50)[0]
    objects = []
    for box in result.boxes:
        cls = int(box.cls.item())
        kind = "cone" if cone and cls == 6 else result.names[cls]
        if (cone and cls != 6) or (not cone and kind not in KINDS):
            continue
        x, y, w, h = box.xywhn[0].tolist()
        objects.append([kind, x, y + h / 2, w, h])
    return objects


def smooth(previous, objects):
    pending = list(previous)
    for obj in objects:
        choices = [(abs(p[1]-obj[1]) + abs(p[2]-obj[2]), i) for i,p in enumerate(pending) if p[0] == obj[0]]
        if choices:
            distance, idx = min(choices)
            if distance < .10:
                prev = pending.pop(idx)
                obj[1:3] = [.7*b + .3*a for a,b in zip(prev[1:3], obj[1:3])]
    return objects


def main():
    import cv2
    import numpy as np
    from ultralytics import YOLO
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, help="Replay locally. Writes annotated MP4 only.")
    parser.add_argument("--output", default="vision-preview.mp4")
    args = parser.parse_args()
    if args.video and args.video.resolve() == Path(args.output).resolve():
        parser.error("Use a separate output file")
    from crosswalk import Crosswalk
    from preview import Preview, hud_feedback
    crossing = Crosswalk()
    vehicle = YOLO("yolo11n.pt")
    cone = YOLO("cone.onnx", task="detect")
    video = cv2.VideoCapture(str(args.video)) if args.video else None
    if video and not video.isOpened():
        raise SystemExit("Cannot open input video")
    preview = Preview(CACHE) if not video else None
    fps = 0.
    writer = None
    last_key = None
    previous = []
    last_stamp = 0
    CACHE.mkdir(parents=True, exist_ok=True)
    last_report = time.monotonic()
    processed = detected = 0
    status = "等待 Jetlink 封包"
    print("Mac Vision 已啟動，等待 ROAD 影像", flush=True)
    try:
        while True:
            if preview:
                preview.show()
                if not preview.running():
                    break
            if not video and time.monotonic() - last_report >= 5:
                print(f"Mac Vision｜近五秒推論 {processed} 幀，含物件 {detected} 幀｜{status}｜{hud_feedback(CACHE)}", flush=True)
                fps = processed / (time.monotonic() - last_report)
                last_report = time.monotonic()
                processed = detected = 0
            if video:
                ok, image = video.read()
                if not ok:
                    break
            else:
                time.sleep(.06)
                try:
                    item = packet_frame((CACHE / "snapshot.packet").read_bytes(), time.time())
                    if not item:
                        status = "收到過期影格"
                        continue
                    if item[0] == last_key:
                        continue
                    last_key, stamp, jpeg = item
                    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                except (KeyError, ValueError, struct.error, OSError, TypeError) as exc:
                    status = f"等待 ROAD：{type(exc).__name__} {exc}"
                    continue
                if image is None:
                    continue
                if stamp - last_stamp > .65:
                    previous = []
                last_stamp = stamp
            objects = smooth(previous, detect(vehicle, image) + detect(cone, image, True))
            previous = objects
            objects = objects + crossing.detect(image)
            if video:
                h, w = image.shape[:2]
                if writer is None:
                    writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"mp4v"), video.get(cv2.CAP_PROP_FPS) or 20, (w,h))
                    if not writer.isOpened():
                        raise SystemExit("Cannot open output video")
                for kind, x,y,_,_ in objects:
                    cv2.putText(image, kind, (int(x*w),int(y*h)), cv2.FONT_HERSHEY_SIMPLEX,.55,(0,210,255),2)
                writer.write(image)
            else:
                processed += 1
                detected += bool(objects)
                latency = (time.time() - stamp) * 1000
                status = f"結果延遲 {latency:.0f} ms，物件 " + (", ".join(o[0] for o in objects) or "0")
                tmp = CACHE / f"vision-{os.getpid()}.tmp"
                tmp.write_text(json.dumps([stamp,objects]))
                tmp.replace(CACHE / "vision.json")
                preview.show(image, objects, stamp, fps)
    finally:
        if video:
            video.release()
        if writer:
            writer.release()
        if preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
