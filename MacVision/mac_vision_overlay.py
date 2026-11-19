"""Place fresh ROAD detections in the native raylib world."""
import json
import math
import os
import time
from pathlib import Path

RESULT = Path(os.environ.get("CARROT_HUD_DIR", Path.home() / "Library/Caches/io.zoompilot.jetlink/carrot-hud")) / "vision.json"


def location(p, u, v, z_offset=0.0):
    # Invert cluster_renderer._camera_overlay_screen_xy on the ground plane.
    a = (u - .5) * p.camera_width / p.focal_length
    b = (v - .5) * p.camera_height / p.focal_length
    rx, ry, rz = p.view_from_road
    aa, ab = rx[0] - a*rz[0], rx[1] - a*rz[1]
    ba, bb = ry[0] - b*rz[0], ry[1] - b*rz[1]
    det = aa*bb - ab*ba
    if abs(det) < 1e-6 or not .02 < v < .98:
        return None
    x_term = (a*rz[2] - rx[2]) * z_offset
    y_term = (b*rz[2] - ry[2]) * z_offset - p.camera_height_m
    forward = (x_term*bb - ab*y_term)/det
    left = (aa*y_term - x_term*ba)/det
    if 1 < forward < 60 and abs(left) < 12:
        return -left, forward


_last_report = 0.


# Local intervals use monotonic time; timestamps shared with the detector use Unix time.
_scene_feedback = None
KINDS = ("person", "crosswalk", "cone", "motorcycle", "bicycle", "car", "bus", "truck")


def read_objects():
    try:
        stamp, objects = json.loads(RESULT.read_bytes())
        if not 0 <= time.time() - stamp < .9:
            return [], "result expired"
        valid = [item for item in objects if isinstance(item, list) and len(item) == 5
                 and item[0] in KINDS and all(isinstance(v, (int, float)) and math.isfinite(v)
                                              for v in item[1:])]
        return valid, "no detections" if not valid else "fresh"
    except (OSError, ValueError, TypeError):
        return [], "waiting for result"


def report_drawn(count, reason):
    global _last_report
    now = time.monotonic()
    if now - _last_report < .25:
        return
    _last_report = now
    tmp = RESULT.with_name(f"drawn-{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps([time.time(), count, reason]))
        tmp.replace(RESULT.with_name("vision-drawn.json"))
    except OSError:
        pass


def draw_icon(rl, kind, x, y):
    if kind == "person":
        rl.draw_circle(x+9, y+4, 4, rl.RAYWHITE)
        for ax, ay, bx, by in ((9,9,9,17),(9,10,3,15),(9,10,16,14),(9,17,4,24),(9,17,15,24)):
            rl.draw_line_ex(rl.Vector2(x+ax,y+ay), rl.Vector2(x+bx,y+by), 3, rl.RAYWHITE)
    elif kind == "crosswalk":
        for i in range(4):
            rl.draw_rectangle(x+i*5, y+5, 3, 15, rl.WHITE)
    elif kind == "cone":
        rl.draw_triangle(rl.Vector2(x+9,y+2), rl.Vector2(x+1,y+21),
                         rl.Vector2(x+17,y+21), rl.ORANGE)
        rl.draw_rectangle(x+5,y+14,8,3,rl.WHITE)
    elif kind in ("motorcycle", "bicycle"):
        rl.draw_circle_lines(x+4,y+18,4,rl.SKYBLUE)
        rl.draw_circle_lines(x+16,y+18,4,rl.SKYBLUE)
        rl.draw_line(x+4,y+18,x+12,y+8,rl.SKYBLUE)
        rl.draw_line(x+12,y+8,x+16,y+18,rl.SKYBLUE)
    else:
        rl.draw_rectangle(x+1,y+10,20,10,rl.LIGHTGRAY)
        rl.draw_rectangle(x+4,y+(3 if kind != "car" else 6),14,8,rl.LIGHTGRAY)
        for dx in (5,17):
            rl.draw_circle(x+dx,y+20,3,rl.GRAY)


def draw_detection_notice(offset_x):
    import pyray as rl
    global _scene_feedback
    if _scene_feedback is None:
        objects, reason = read_objects()
        count = 0
        if objects:
            reason = "2D view"
    else:
        objects, count, reason = _scene_feedback
        _scene_feedback = None
    report_drawn(count, reason)
    if objects:
        # Fixed legend: these icons indicate camera detections, never lane positions.
        kinds = {item[0] for item in objects}
        x, y = round(offset_x) + 23, 209
        rl.draw_rectangle(x, y, 64 + 31*len(kinds), 34, rl.DARKGRAY)
        rl.draw_text("ROAD", x+6, y+9, 17, rl.RAYWHITE)
        x += 60
        for kind in KINDS:
            if kind in kinds:
                draw_icon(rl, kind, x, y+4)
                x += 31


def draw(renderer, state, shift, ego_y):
    global _scene_feedback
    objects, reason = read_objects()
    drawn = 0
    if objects:
        try:
            drawn, reason = draw_world(renderer, state, shift, ego_y, objects)
        except (ValueError, TypeError, AttributeError, IndexError, ZeroDivisionError) as error:
            reason = f"projection: {type(error).__name__}"
    _scene_feedback = (objects, drawn, reason)


def draw_world(renderer, state, shift, ego_y, objects):
    import pyray as rl
    angles = state.camera_calibration_euler
    if angles is None or len(angles) != 3 or not all(map(math.isfinite, angles)):
        return 0, "no camera calibration"
    p = renderer._camera_overlay_projection(state)
    if p is None or p.wide_camera:
        return 0, "no ROAD projection"
    drawn = 0
    for kind,u,v,w,h in objects[:32]:
        if not 0 < u < 1:
            continue
        point = location(p, u, v, renderer.camera_overlay_z_offset_m)
        if point is None:
            continue
        x, y = point[0]-shift, point[1]+ego_y
        def pos(dx,dy,z):
            return rl.Vector3(x+dx,y+dy,z)
        def upright(z1,z2,r1,r2,color):
            rl.draw_cylinder_ex(pos(0,0,z1),pos(0,0,z2),r1,r2,12,color)
        if kind == "crosswalk":
            for stripe in range(-2, 3):
                rl.draw_cube(pos(stripe*.38,0,.04),.22,1.0,.06,rl.RAYWHITE)
        elif kind == "cone":
            rl.draw_cube(pos(0,0,.045),.52,.52,.09,rl.DARKGRAY)
            upright(.08,.58,.23,.035,rl.ORANGE)
            upright(.25,.34,.135,.105,rl.WHITE)
        elif kind == "person":
            for side in (-1, 1):
                rl.draw_cylinder_ex(pos(side*.10,0,.79),pos(side*.15,0,.08),.10,.075,8,rl.LIGHTGRAY)
                rl.draw_cylinder_ex(pos(side*.18,0,1.29),pos(side*.29,0,.89),.075,.065,8,rl.SKYBLUE)
            upright(.73,1.4,.18,.23,rl.SKYBLUE)
            rl.draw_sphere(pos(0,0,1.53),.16,rl.RAYWHITE)
        elif kind in ("motorcycle","bicycle"):
            for dy in (-.52,.52):
                rl.draw_cylinder_ex(pos(-.09,dy,.29),pos(.09,dy,.29),.29,.29,12,rl.DARKGRAY)
            rl.draw_cube(pos(0,0,.64),.36,1.05,.34,rl.SKYBLUE)
        elif kind in ("car","bus","truck"):
            large = kind != "car"
            rl.draw_cube(pos(0,0,.64),2 if large else 1.7,5 if large else 3.7,1.1,rl.GRAY)
            if kind == "truck":
                rl.draw_cube(pos(0,.45,1.55),1.96,3.9,1.45,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,-1.75,1.32),1.88,1.05,.88,rl.SKYBLUE)
            elif kind == "bus":
                rl.draw_cube(pos(0,0,1.55),1.92,4.85,1.3,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,0,1.73),1.94,4.52,.42,rl.DARKBLUE)
            else:
                rl.draw_cube(pos(0,0,1.35),1.44,2.10,.52,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,-1.06,1.36),1.28,.04,.32,rl.DARKBLUE)
        drawn += 1
    if not drawn:
        return 0, "outside ground view"
    return drawn, "estimated height" if state.road_transform_trans is None else "projected"
