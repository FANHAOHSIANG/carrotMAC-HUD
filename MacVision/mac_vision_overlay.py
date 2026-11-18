"""Place fresh ROAD detections in the native raylib world."""
import json
import math
import os
import time
from pathlib import Path

RESULT = Path(os.environ.get("CARROT_HUD_DIR", Path.home() / "Library/Caches/io.zoompilot.jetlink/carrot-hud")) / "vision.json"


def location(p, u, v):
    # Invert cluster_renderer._camera_overlay_screen_xy on the ground plane.
    a = (u - .5) * p.camera_width / p.focal_length
    b = (v - .5) * p.camera_height / p.focal_length
    rx, ry, rz = p.view_from_road
    aa, ab = rx[0] - a*rz[0], rx[1] - a*rz[1]
    ba, bb = ry[0] - b*rz[0], ry[1] - b*rz[1]
    det = aa*bb - ab*ba
    if abs(det) < 1e-6 or not .02 < v < .98:
        return None
    forward, left = ab*p.camera_height_m/det, -aa*p.camera_height_m/det
    if 1 < forward < 60 and abs(left) < 12:
        return -left, forward


_last_report = 0.


def report_drawn(count):
    global _last_report
    now = time.monotonic()
    if now-_last_report >= .25:
        _last_report = now
        tmp = RESULT.with_name(f"drawn-{os.getpid()}.tmp")
        tmp.write_text(json.dumps([now,count]))
        tmp.replace(RESULT.with_name("vision-drawn.json"))


def draw_crosswalk_notice():
    import pyray as rl
    try:
        stamp, objects = json.loads(RESULT.read_bytes())
        if 0 <= time.monotonic()-stamp < .9 and any(o[0] == "crosswalk" for o in objects):
            rl.draw_rectangle(18, 72, 148, 32, rl.DARKGRAY)
            for i in range(4):
                rl.draw_rectangle(24+i*5, 81, 3, 14, rl.WHITE)
            rl.draw_text("CROSSWALK", 52, 80, 17, rl.YELLOW)
    except (OSError, ValueError, TypeError, IndexError):
        pass


def draw(renderer, state, shift, ego_y):
    import pyray as rl
    try:
        stamp, objects = json.loads(RESULT.read_bytes())
        if not 0 <= time.monotonic() - stamp < .9 or not objects:
            report_drawn(0)
            return
        if state.camera_calibration_euler is None or state.road_transform_trans is None:
            return
        p = renderer._camera_overlay_projection(state)
        if p is None or p.wide_camera:
            return
        drawn = 0
        for kind,u,v,w,h in objects[:32]:
            if kind == "crosswalk":
                continue
            if not all(map(math.isfinite,(u,v,w,h))) or not 0 < u < 1:
                continue
            point = location(p,u,v)
            if point is None:
                continue
            x, y = point[0]-shift, point[1]+ego_y
            def pos(dx,dy,z):
                return rl.Vector3(x+dx,y+dy,z)
            def upright(z1,z2,r1,r2,color):
                rl.draw_cylinder_ex(pos(0,0,z1),pos(0,0,z2),r1,r2,12,color)
            if kind == "cone":
                upright(0,.52,.22,.035,rl.ORANGE)
                upright(.25,.34,.135,.105,rl.WHITE)
            elif kind == "person":
                upright(.08,1.35,.17,.21,rl.LIGHTGRAY)
                rl.draw_sphere(pos(0,0,1.53),.16,rl.RAYWHITE)
            elif kind in ("motorcycle","bicycle"):
                for dy in (-.52,.52):
                    rl.draw_cylinder_ex(pos(-.09,dy,.29),pos(.09,dy,.29),.29,.29,12,rl.DARKGRAY)
                rl.draw_cube(pos(0,0,.64),.36,1.05,.34,rl.SKYBLUE)
            elif kind in ("car","bus","truck"):
                large = kind != "car"
                rl.draw_cube(pos(0,0,.64),2 if large else 1.7,5 if large else 3.7,1.1,rl.GRAY)
                rl.draw_cube(pos(0,0,1.45),1.8 if large else 1.4,4.8 if large else 2.1,1.1 if large else .55,rl.LIGHTGRAY)
            drawn += 1
        report_drawn(drawn)
    except (OSError, ValueError, TypeError, AttributeError, IndexError, ZeroDivisionError):
        return
