"""Decode the pinned Tony/kairess YOLOv5 crosswalk head (image space only)."""
import math


def best_box(rows, width, height, pad_x, pad_y):
    best = None
    score = .5
    for cx, cy, w, h, obj, zebra, _, _ in rows:
        confidence = obj * zebra
        if not score <= confidence <= 1 or not all(map(math.isfinite, (cx, cy, w, h))):
            continue
        x0, x1 = max(0, (cx-w/2-pad_x)/width), min(1, (cx+w/2-pad_x)/width)
        y0, y1 = max(0, (cy-h/2-pad_y)/height), min(1, (cy+h/2-pad_y)/height)
        if x1 > x0 and y1 > y0:
            # ONNX coordinates can be NumPy scalars. Emit ordinary JSON numbers.
            best = ["crosswalk", float((x0+x1)/2), float(y1),
                    float(x1-x0), float(y1-y0)]
            score = confidence
    return [best] if best else []


class Crosswalk:
    def __init__(self):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession("crosswalk.onnx", opts, providers=["CPUExecutionProvider"])

    def detect(self, image):
        import cv2
        import numpy as np
        h, w = image.shape[:2]
        ratio = 320/max(h,w)
        rw, rh = max(1,round(w*ratio)), max(1,round(h*ratio))
        x, y = (320-rw)//2, (320-rh)//2
        canvas = np.full((320,320,3), 114, dtype=np.uint8)
        canvas[y:y+rh,x:x+rw] = cv2.resize(image, (rw,rh))
        tensor = cv2.dnn.blobFromImage(canvas, 1/255., swapRB=True)
        out, = self.session.run(["output0"], {"images": tensor})
        if out.shape != (1,6375,8):
            raise ValueError(f"Unexpected crosswalk model output {out.shape}")
        rows = out[0]
        return best_box(rows[rows[:,4]*rows[:,5] >= .5], rw, rh, x, y)
