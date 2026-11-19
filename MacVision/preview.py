"""Local operator display. No network listener or camera access."""
import json
import time


def hud_feedback(cache):
    try:
        stamp, count, reason = json.loads((cache/"vision-drawn.json").read_bytes())
        if 0 <= time.time() - stamp < 2:
            return f"HUD 3D: {count} | {reason}"
    except (OSError, ValueError, TypeError):
        pass
    return "HUD: awaiting renderer"


class Preview:
    def __init__(self, cache):
        import cv2
        self.title = "Carrot Vision | USB"
        self.cache = cache
        self.last = 0
        cv2.namedWindow(self.title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.title, 880, 340)

    def show(self, image=None, objects=(), stamp=None, fps=0):
        import cv2
        import numpy as np
        now = time.monotonic()
        if image is None and now-self.last < .9:
            return
        panel = np.zeros((340,880,3), dtype=np.uint8)
        def label(s,x,y):
            cv2.putText(panel,s,(x,y),cv2.FONT_HERSHEY_SIMPLEX,.55,(220,224,232),1,cv2.LINE_AA)
        if image is None:
            label("Waiting for fresh ROAD image", 20,160)
        else:
            panel[:320,:512] = cv2.resize(image,(512,320))
            for kind,x,y,w,h in objects:
                a,b = int((x-w/2)*512), int((y-h)*320)
                cv2.rectangle(panel,(a,b),(int((x+w/2)*512),int(y*320)),(90,220,220),1)
                label(kind,max(2,a),max(18,b))
            self.last = now
        label("USB ROAD / Mac inference",530,36)
        label(f"{fps:.1f} fps",530,75)
        if stamp is not None:
            label(f"Capture to result: {(time.time()-stamp)*1000:.0f} ms",530,105)
            label(f"Detected: {len(objects)}",530,137)
        label(hud_feedback(self.cache),530,178)
        cv2.imshow(self.title,panel)

    def running(self):
        import cv2
        return cv2.waitKey(1) not in (27,ord("q")) and cv2.getWindowProperty(self.title,cv2.WND_PROP_VISIBLE) >= 1
