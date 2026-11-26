"""Mac front-camera recognition worker. All coordinates are image-relative."""
import argparse
import base64
import json
import math
import os
import struct
import time
from pathlib import Path

CACHE = Path(os.environ.get("CARROT_HUD_DIR", Path.home() / "Library/Caches/io.zoompilot.jetlink/carrot-hud"))
KINDS = {"person", "motorcycle", "bicycle", "car", "truck", "bus"}


def frame_identity(frame):
    if not isinstance(frame, dict):
        return None
    frame_id = frame.get("frame")
    captured = "capture_time" in frame
    source_time = frame.get("capture_time" if captured else "time")
    if (type(frame_id) is not int or frame_id < 0 or type(source_time) not in (int, float)
            or not math.isfinite(source_time) or source_time < 0):
        return None
    return frame_id, source_time, "capture" if captured else "preview"


def packet_frame(data, wall_now):
    received, = struct.unpack_from("<d", data)
    packet = json.loads(data[8:])
    cameras = packet["cameras"]
    low, high = cameras.get("road"), cameras.get("road_hd")
    low_key, high_key = frame_identity(low), frame_identity(high)
    # The C4 creates both JPEGs from the same full ROAD image. Prefer native
    # displayed ROAD preview if a sender presents conflicting capture identities.
    use_hd = high_key is not None and (low is None or high_key == low_key)
    frame, key = (high, high_key) if use_hd else (low, low_key)
    if key is None:
        return None
    age = packet["sent"] - key[1]
    # Both Python processes share Unix time, even with different macOS runtimes.
    receipt_age = wall_now - received
    if not (0 <= receipt_age < .5 and 0 <= age < .4):
        return None
    return key, received - age, base64.b64decode(frame["jpeg"], validate=True)


def publish_results(cache, key, stamp, scene_objects, frame_objects):
    # Each file is independently complete. Older HUDs continue reading the
    # smoothed scene list. Camera-view HUDs match unsmoothed coordinates to
    # the C4 frame they actually displayed.
    frame_id, source_time, time_kind = key
    packet = {"version": 2, "camera": "road", "frame_id": frame_id,
              "source_time": source_time, "time_kind": time_kind,
              "stamp": stamp, "objects": frame_objects}
    for name, value in (("vision", [stamp, scene_objects]), ("vision-frame", packet)):
        tmp = cache / f"{name}-{os.getpid()}.tmp"
        tmp.write_text(json.dumps(value))
        tmp.replace(cache / f"{name}.json")


def box_iou(a, b):
    """Intersection over union for normalized bottom-center boxes."""
    _, x, y, w, h = a
    _, u, v, bw, bh = b
    iw = max(0., min(x+w/2, u+bw/2) - max(x-w/2, u-bw/2))
    ih = max(0., min(y, v) - max(y-h, v-bh))
    overlap = iw * ih
    union = w*h + bw*bh - overlap
    return overlap / union if union > 0 else 0.


def riding(person, bike):
    _, x, foot, w, h = person
    _, cx, bottom, bw, bh = bike
    return (abs(x-cx) <= .26*bw and w <= 1.15*bw and
            bottom-1.05*bh <= foot <= bottom-.06*bh and
            foot-h < bottom-.8*bh)


class RoadDetections:
    """Use current motorcycle evidence and the immediately preceding ROAD frame."""
    def __init__(self):
        self.stamp = None
        self.bikes = []

    def resolve(self, scored, stamp):
        recent = self.bikes if self.stamp is not None and 0 < stamp-self.stamp < .55 else []
        bikes = []
        for box, score in scored:
            if box[0] != "motorcycle":
                continue
            corroborated = any(box_iou(box, previous) >= .42 for previous in recent)
            if score >= .50 or corroborated:
                bikes.append((box, score, corroborated))
        # Weak isolated detections can establish a match on the next capture.
        self.bikes = [box for box, score in scored if box[0] == "motorcycle" and score >= .35]
        self.stamp = stamp
        riders = [box for box, score in scored if box[0] == "person" and score >= .50]
        output = []
        for box, score in scored:
            kind = box[0]
            if kind == "motorcycle":
                if any(box is bike for bike, _, _ in bikes):
                    output.append(box)
            elif score >= .50:
                if kind == "person":
                    matches = [bike for bike, _, _ in bikes if riding(box, bike)]
                    if len(matches) == 1 and sum(riding(p, matches[0]) for p in riders) == 1:
                        continue
                if kind == "car" and any(stable and strength >= score and box_iou(box, bike) >= .75
                                         for bike, strength, stable in bikes):
                    continue
                output.append(box)
        return output


def detect(model, image, cone=False, road=None, stamp=None):
    # Fixed-shape cone ONNX uses a square letterbox. Ultralytics maps the
    # boxes back to the original aspect ratio before exposing xywhn.
    classes = [6] if cone else [0, 1, 2, 3, 5, 7]
    result = model.predict(image, device="cpu", verbose=False, imgsz=640,
                           rect=not cone, classes=classes, conf=.35 if road is not None else .50)[0]
    objects = []
    for box in result.boxes:
        cls = int(box.cls.item())
        kind = "cone" if cone and cls == 6 else result.names[cls]
        if (cone and cls != 6) or (not cone and kind not in KINDS):
            continue
        x, y, w, h = box.xywhn[0].tolist()
        obj = [kind, x, y + h / 2, w, h]
        objects.append((obj, float(box.conf.item())) if road is not None else obj)
    return road.resolve(objects, stamp) if road is not None else objects


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
    parser.add_argument("--background", action="store_true", help="Run without a preview window")
    args = parser.parse_args()
    log = print
    if args.background:
        import logging
        from logging.handlers import RotatingFileHandler
        logger = logging.getLogger("carrot.vision")
        logger.setLevel(logging.INFO)
        logger.addHandler(RotatingFileHandler("worker.log", maxBytes=262144, backupCount=1, encoding="utf-8"))
        log = logger.info
    if not args.video:
        import fcntl
        CACHE.mkdir(parents=True, exist_ok=True)
        lock = (CACHE / "vision-worker.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if args.background:
                raise SystemExit(75)
            raise SystemExit("Mac Vision 已在執行。如需預覽，請先關閉登入自動啟動。")
    if args.video and args.video.resolve() == Path(args.output).resolve():
        parser.error("Use a separate output file")
    from crosswalk import Crosswalk
    from preview import Preview, hud_feedback
    crossing = Crosswalk()
    road = RoadDetections()
    vehicle = YOLO("yolo11n.pt")
    cone = YOLO("cone.onnx", task="detect")
    video = cv2.VideoCapture(str(args.video)) if args.video else None
    if video and not video.isOpened():
        raise SystemExit("Cannot open input video")
    preview = Preview(CACHE) if not video and not args.background else None
    fps = 0.
    writer = None
    last_key = None
    previous = []
    last_stamp = 0
    CACHE.mkdir(parents=True, exist_ok=True)
    last_report = time.monotonic()
    processed = detected = 0
    status = "等待 Jetlink 封包"
    log("Mac Vision 已啟動，等待 ROAD 影像")
    try:
        while True:
            if preview:
                preview.show()
                if not preview.running():
                    break
            if not video and time.monotonic() - last_report >= 5:
                log(f"Mac Vision｜近五秒推論 {processed} 幀，含物件 {detected} 幀｜{status}｜{hud_feedback(CACHE)}")
                fps = processed / (time.monotonic() - last_report)
                last_report = time.monotonic()
                processed = detected = 0
            if video:
                ok, image = video.read()
                if not ok:
                    break
                stamp = video.get(cv2.CAP_PROP_POS_FRAMES) / (video.get(cv2.CAP_PROP_FPS) or 20.)
            else:
                try:
                    item = packet_frame((CACHE / "snapshot.packet").read_bytes(), time.time())
                    if not item:
                        time.sleep(.25 if args.background else .025)
                        status = "收到過期影格"
                        continue
                    if item[0] == last_key:
                        time.sleep(.015)
                        continue
                    last_key, stamp, jpeg = item
                    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                except (KeyError, ValueError, struct.error, OSError, TypeError) as exc:
                    time.sleep(.25 if args.background else .025)
                    status = f"等待 ROAD：{type(exc).__name__} {exc}"
                    continue
                if image is None:
                    continue
                if stamp - last_stamp > .65:
                    previous = []
                last_stamp = stamp
            start = time.perf_counter()
            vehicles = detect(vehicle, image, road=road, stamp=stamp)
            after_vehicle = time.perf_counter()
            cones = detect(cone, image, True)
            after_cone = time.perf_counter()
            frame_objects = vehicles + cones
            objects = smooth(previous, [obj.copy() for obj in frame_objects])
            previous = objects
            crosswalks = crossing.detect(image)
            objects = objects + crosswalks
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
                status = (f"ROAD {image.shape[1]}×{image.shape[0]}，結果延遲 {latency:.0f} ms"
                          f"，車人 {(after_vehicle-start)*1000:.0f} / 錐 {(after_cone-after_vehicle)*1000:.0f}"
                          f" / 斑馬線與後處理 {(time.perf_counter()-after_cone)*1000:.0f} ms"
                          "，物件 " + (", ".join(o[0] for o in objects) or "0"))
                publish_results(CACHE, last_key, stamp, objects, frame_objects + crosswalks)
                if preview:
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
