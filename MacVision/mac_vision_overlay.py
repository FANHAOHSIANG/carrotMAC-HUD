"""Place fresh ROAD detections in the native raylib world."""
import json
import math
import os
import time
from pathlib import Path

RESULT = Path(os.environ.get("CARROT_HUD_DIR", Path.home() / "Library/Caches/io.zoompilot.jetlink/carrot-hud")) / "vision.json"


from hud_road_edges import outside_road


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
_placed_icons = None
KINDS = ("person", "crosswalk", "cone", "motorcycle", "bicycle", "car", "bus", "truck")
# Heights place the leader just above its observed body. The horizontal and
# longitudinal coordinates always originate in the ROAD image.
ICON_HEIGHT_M = {"car": 1.6, "bus": 2.55, "truck": 2.55, "motorcycle": 1.35,
                 "bicycle": 1.25, "person": 1.8, "cone": .7, "crosswalk": .1}
RESULT_MAX_AGE = .9


def read_objects():
    try:
        stamp, objects = json.loads(RESULT.read_bytes())
        if not 0 <= time.time() - stamp < RESULT_MAX_AGE:
            return [], "result expired", None
        valid = [item for item in objects if isinstance(item, list) and len(item) == 5
                 and item[0] in KINDS and all(isinstance(v, (int, float)) and math.isfinite(v)
                                              for v in item[1:])]
        return valid, "no detections" if not valid else "fresh", stamp
    except (OSError, ValueError, TypeError):
        return [], "waiting for result", None


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


def begin_frame():
    global _scene_feedback, _placed_icons
    _scene_feedback = _placed_icons = None


def draw_detection_notice(offset_x):
    import pyray as rl
    if _scene_feedback is None:
        objects, reason, _ = read_objects()
        count = 0
        if objects:
            reason = "2D view"
    else:
        objects, count, reason = _scene_feedback
    placed = 0
    if _placed_icons is not None:
        stamp, drawn = _placed_icons
        if 0 <= time.time() - stamp < RESULT_MAX_AGE:
            placed = drawn
            reason += f" | icons {placed}"
    begin_frame()
    report_drawn(count, reason)
    if objects:
        # Fixed legend: these icons indicate camera detections, never lane positions.
        kinds = {item[0] for item in objects}
        x, y = round(offset_x) + 23, 209
        header = f"ROAD {placed}" if placed else "ROAD"
        header_w = 60 + (6 + len(str(placed))*12 if placed else 0)
        rl.draw_rectangle(x, y, header_w + 4 + 31*len(kinds), 34, rl.DARKGRAY)
        rl.draw_text(header, x+6, y+9, 17, rl.RAYWHITE)
        x += header_w
        for kind in KINDS:
            if kind in kinds:
                draw_icon(rl, kind, x, y+4)
                x += 31


class VehicleMatches:
    """One visible body per matched ROAD/native target; confirm class separately."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.stamp = None
        self.previous = []
        self.current = []
        self.previous_free = []
        self.current_free = []

    def match(self, stamp, points, targets):
        if stamp != self.stamp:
            recent = self.stamp is not None and 0 < stamp - self.stamp < .55
            self.previous = self.current if recent else []
            self.previous_free = self.current_free if recent else []
            self.stamp = stamp
        candidates = []
        nearby_previous = [
            [kind for kind, px, py in self.previous if abs(tx - px) < .85 and abs(ty - py) < 3.2]
            for tx, ty in targets
        ]
        for i, (kind, x, y) in enumerate(points):
            if kind not in ("car", "truck", "bus", "motorcycle"):
                continue
            for j, (tx, ty) in enumerate(targets):
                # Reuse a recent isolated match through modest projection jitter.
                previous_kinds = nearby_previous[j]
                lateral = 1.15 if previous_kinds else .85
                fore = min(3.2, 1.5 + .045*y) * (1.25 if previous_kinds else 1.)
                dx, dy = abs(x - tx), abs(y - ty)
                if dx < lateral and dy < fore:
                    candidates.append(((dx / lateral)**2 + (dy / fore)**2, i, j, previous_kinds))
        matched = {}
        bikes = set()
        used = set()
        self.current = []
        for _, i, j, previous_kinds in sorted(candidates):
            if i in matched or j in used:
                continue
            matched[i] = j
            used.add(j)
            # An ambiguous observation can suppress one duplicate body, but cannot
            # change a native car into a motorcycle or corroborate the next frame.
            if any((k == i or n == j) and (k, n) != (i, j) for _, k, n, _ in candidates):
                continue
            kind = points[i][0]
            if kind == "motorcycle" and "motorcycle" in previous_kinds:
                bikes.add(i)
            self.current.append((kind, *targets[j]))
        # Only draw an unpaired car after observations in two successive captures.
        # A missed capture ends that admission. Re-reading vision.json at HUD
        # refresh rate cannot turn a single detector frame into multiple hits.
        standalone = [(i, x, y) for i, (kind, x, y) in enumerate(points)
                      if kind in ("car", "truck", "bus") and i not in matched]
        self.current_free = [(x, y) for _, x, y in standalone]
        free_pairs = []
        for i, x, y in standalone:
            for j, (px, py) in enumerate(self.previous_free):
                dx, dy = abs(x - px), abs(y - py)
                if dx < .85 and dy < 3.2:
                    free_pairs.append(((dx/.85)**2 + (dy/3.2)**2, i, j))
        free = set()
        used_previous = set()
        for _, i, j in sorted(free_pairs):
            if i not in free and j not in used_previous:
                free.add(i)
                used_previous.add(j)
        return matched, bikes, free


_matches = VehicleMatches()


def draw(renderer, state, shift, _ego_y, native=()):
    global _scene_feedback
    begin_frame()
    renderer._mac_vision_scene_icons = None
    objects, reason, stamp = read_objects()
    drawn = 0
    drawn_bikes = set()
    if stamp is None:
        _matches.reset()
    elif not objects:
        _matches.match(stamp, [], [])
    else:
        try:
            drawn, reason = draw_world(renderer, state, shift, objects, stamp, native, drawn_bikes)
        except (ValueError, TypeError, AttributeError, IndexError, ZeroDivisionError) as error:
            reason = f"projection: {type(error).__name__}"
    _scene_feedback = (objects, drawn, reason)
    return drawn_bikes


def has_scene_icons(renderer):
    return bool(getattr(renderer, "_mac_vision_scene_icons", None))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _camera_objects(renderer, display_frame):
    if not isinstance(display_frame, (tuple, list)) or len(display_frame) != 4:
        return ()
    camera, frame_id, frame_time, time_kind = display_frame
    if (camera != "road" or type(frame_id) is not int or frame_id < 0
            or not _number(frame_time) or time_kind not in ("capture", "preview")):
        return ()
    path = RESULT.with_name("vision-frame.json")
    try:
        stat = path.stat()
        signature = (path, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        if not 0 < stat.st_size <= 65536:
            return ()
        cache = getattr(renderer, "_mac_vision_camera_packet", None)
        if cache is None or cache[0] != signature:
            packet = json.loads(path.read_bytes())
            renderer._mac_vision_camera_packet = signature, packet
        else:
            packet = cache[1]
    except (OSError, ValueError):
        return ()
    if not isinstance(packet, dict) or packet.get("version") != 2 or packet.get("camera") != camera:
        return ()
    detected_id, detected_time, stamp = packet.get("frame_id"), packet.get("source_time"), packet.get("stamp")
    if (type(detected_id) is not int or detected_id < 0 or not _number(detected_time)
            or packet.get("time_kind") != time_kind or not _number(stamp)
            or not 0 <= time.time() - stamp < RESULT_MAX_AGE):
        return ()
    exact_frame = frame_id == detected_id and frame_time == detected_time
    # Legacy preview time measures JPEG creation and cannot establish capture skew.
    near_frame = time_kind == "capture" and frame_id > detected_id and 0 < frame_time - detected_time <= .25
    if not (exact_frame or near_frame):
        return ()
    rows = packet.get("objects")
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows[:32] if isinstance(row, list) and len(row) == 5
                 and row[0] in KINDS and all(_number(v) for v in row[1:])
                 and 0 <= row[1] <= 1 and 0 <= row[2] <= 1 and 0 < row[3] <= 1 and 0 < row[4] <= 1)


def has_camera_icons(renderer, display_frame):
    return bool(_camera_objects(renderer, display_frame))


def draw_camera_icons(renderer, state, projection, display_frame, metric_rects=()):
    """Place unsmoothed ROAD detections on a verified live film capture."""
    global _scene_feedback, _placed_icons
    if projection is None or projection.wide_camera or not getattr(state, "onroad", False):
        return 0
    objects = _camera_objects(renderer, display_frame)
    if not objects:
        return 0
    from cluster_config import DESIGN_HEIGHT
    from mac_vision_icons import draw_class_icons

    view, video = projection.dest, projection.video_dest
    left, top, right, bottom = view.x, view.y, view.x + view.width, view.y + view.height
    anchors = []
    for kind, u, v, w, h in sorted(objects, key=lambda row: row[2], reverse=True):
        x1 = max(left, video.x + (u - w / 2) * video.width)
        x2 = min(right, video.x + (u + w / 2) * video.width)
        y1 = max(top, video.y + (v - h) * video.height)
        y2 = min(bottom, video.y + v * video.height)
        if x2 > x1 and y2 > y1:
            anchors.append((kind, (x1 + x2) / 2, y1))
    placed = draw_class_icons(anchors, (left, top, right, bottom),
                              36 * renderer.height / DESIGN_HEIGHT, metric_rects)
    if placed:
        _placed_icons = renderer._mac_vision_camera_packet[1]["stamp"], placed
        _scene_feedback = objects, 0, "2D view"
    return placed


def draw_scene_icons(renderer, state, camera, bounds, metric_rects=()):
    """Draw this scene's fresh observations in its native label coordinates."""
    global _placed_icons
    observations = getattr(renderer, "_mac_vision_scene_icons", None)
    renderer._mac_vision_scene_icons = None
    if not observations:
        return 0
    stamp, points = observations
    if not 0 <= time.time() - stamp < RESULT_MAX_AGE:
        return 0
    import pyray as rl
    from cluster_config import DESIGN_HEIGHT
    from cluster_renderer import world_to_screen_label_anchor
    from cluster_scene import render_scene_forward_m
    from mac_vision_icons import draw_class_icons

    anchors = []
    for kind, right, forward in sorted(points, key=lambda p: p[2]):
        point = rl.Vector3(right, render_scene_forward_m(forward, state), ICON_HEIGHT_M[kind])
        screen = world_to_screen_label_anchor(point, camera, renderer.width, renderer.height)
        if screen is not None:
            anchors.append((kind, screen.x, screen.y))
    placed = draw_class_icons(anchors, bounds, 36 * renderer.height / DESIGN_HEIGHT, metric_rects)
    if placed:
        _placed_icons = stamp, placed
    return placed


def draw_world(renderer, state, shift, objects, stamp, native, drawn_bikes):
    import pyray as rl
    angles = state.camera_calibration_euler
    if angles is None or len(angles) != 3 or not all(map(math.isfinite, angles)):
        _matches.reset()
        return 0, "no camera calibration"
    p = renderer._camera_overlay_projection(state)
    if p is None or p.wide_camera:
        _matches.reset()
        return 0, "no ROAD projection"
    drawn = 0
    points = []
    for kind,u,v,w,h in objects[:32]:
        if not 0 < u < 1:
            continue
        point = location(p, u, v, renderer.camera_overlay_z_offset_m)
        if point is None:
            continue
        if outside_road(state, *point):
            continue
        points.append((kind, *point))
    # Native center.y is a rendered distance (half scale in 3D plus a lead
    # bumper offset). The ROAD contact point and longitudinal_m use real meters.
    age = max(0., time.time() - stamp)
    targets = []
    native_indices = []
    for index, vehicle in enumerate(native):
        distance = vehicle.longitudinal_m
        if not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
            continue
        speed = vehicle.relative_speed_mps
        if isinstance(speed, (int, float)) and math.isfinite(speed):
            distance -= speed * age
        targets.append((vehicle.center.x + shift, distance))
        native_indices.append(index)
    merged, bikes, standalone = _matches.match(stamp, points, targets)
    # The existing two-capture rule admits an unmatched car-like object. A
    # ROAD observation paired with an existing car already has corroboration.
    # Keep each icon at the measured ROAD position, including the matched ones.
    admitted = tuple(point for i, point in enumerate(points)
                     if point[0] not in ("car", "truck", "bus") or i in merged or i in standalone)
    if admitted:
        renderer._mac_vision_scene_icons = stamp, admitted
    from cluster_scene import render_scene_forward_m
    for i, (kind, right, forward) in enumerate(points):
        if i in merged:
            if i not in bikes:
                continue
            index = native_indices[merged[i]]
            vehicle = native[index]
            if native_road_vehicle(vehicle):
                draw_native_bike(rl, vehicle)
                drawn_bikes.add(index)
                drawn += 1
            continue
        if kind in ("car", "truck", "bus") and i not in standalone:
            continue
        x, y = right-shift, render_scene_forward_m(forward, state)
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
            upright(.73,1.4,.18,.23,rl.Color(142, 186, 209, 255))
            rl.draw_sphere(pos(0,0,1.53),.16,rl.RAYWHITE)
        elif kind in ("motorcycle","bicycle"):
            for dy in (-.52,.52):
                rl.draw_cylinder_ex(pos(-.09,dy,.29),pos(.09,dy,.29),.29,.29,12,rl.DARKGRAY)
            if kind == "motorcycle":
                rl.draw_cube(pos(0,0,.63),.44,1.12,.40,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,-.18,.88),.32,.65,.12,rl.DARKGRAY)
            else:
                for a,b in (((0,-.52,.29),(0,-.12,.77)),((0,-.12,.77),(0,.12,.32)),
                            ((0,.12,.32),(0,-.52,.29)),((0,.12,.32),(0,.43,.81)),
                            ((0,.43,.81),(0,.52,.29)),((0,-.12,.77),(0,.43,.81))):
                    rl.draw_cylinder_ex(pos(*a),pos(*b),.035,.035,6,rl.SKYBLUE)
        elif kind in ("car","bus","truck"):
            large = kind != "car"
            length = 5. if large else 3.7
            # The visible ground contact locates the near face of this proxy.
            # Centering a whole car on it lets its body protrude toward the ego.
            y += length / 2
            rl.draw_cube(pos(0,0,.64),2 if large else 1.7,length,1.1,rl.GRAY)
            for dx in (-1.,1.):
                for dy in (-1.,1.):
                    wheel_x = dx*(.96 if large else .84)
                    wheel_y = dy*(1.65 if large else 1.15)
                    rl.draw_cylinder_ex(pos(wheel_x-.07,wheel_y,.34),pos(wheel_x+.07,wheel_y,.34),
                                        .34,.34,10,rl.DARKGRAY)
            if kind == "truck":
                rl.draw_cube(pos(0,.45,1.55),1.96,3.9,1.45,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,-1.75,1.32),1.88,1.05,.88,rl.SKYBLUE)
            elif kind == "bus":
                rl.draw_cube(pos(0,0,1.55),1.92,4.85,1.3,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,0,1.73),1.94,4.52,.42,rl.Color(61, 81, 100, 255))
            else:
                rl.draw_cube(pos(0,0,1.35),1.44,2.10,.52,rl.LIGHTGRAY)
                rl.draw_cube(pos(0,-1.06,1.36),1.28,.04,.32,rl.Color(61, 81, 100, 255))
        drawn += 1
    if merged:
        return drawn, f"projected | matched {len(merged)} native | bikes {len(drawn_bikes)}"
    if not drawn:
        return 0, "outside ground view"
    return drawn, "estimated height" if state.road_transform_trans is None else "projected"


def native_road_vehicle(vehicle):
    source = vehicle.source
    return (source.startswith("modelV2") or source.partition("+radar:")[0] == "radarState"
            or bool(source and (vehicle.primary or vehicle.cut_in)
                    and vehicle.longitudinal_m is not None and vehicle.longitudinal_m > 0))


def draw_native_bike(rl, vehicle):
    def pos(side, fore, z):
        return rl.Vector3(vehicle.center.x + side*vehicle.right_x + fore*vehicle.forward_x,
                          vehicle.center.y + side*vehicle.right_y + fore*vehicle.forward_y, z)

    alpha = int(80 + 150 * max(0., min(1., vehicle.confidence)))
    for fore in (-.59, .59):
        rl.draw_cylinder_ex(pos(-.085, fore, .29), pos(.085, fore, .29), .29, .29, 10, rl.DARKGRAY)
    rl.draw_cylinder_ex(pos(0, -.38, .60), pos(0, .37, .74), .20, .25, 8,
                        rl.Color(*vehicle.body_color[:3], alpha))
    rl.draw_cylinder_ex(pos(0, -.39, .65), pos(0, -.39, .81), .18, .14, 8,
                        rl.Color(*vehicle.rear_color[:3], alpha))


def draw_native_car(renderer, vehicle, vector):
    """Silhouette for the existing forward vehicle marker, using its native pose and tint."""

    w, length, height = vehicle.width_m, vehicle.length_m, vehicle.height_m
    alpha = int(80 + 150 * max(0., min(1., vehicle.confidence)))

    def corner(side, fore, up):
        return vector(vehicle.center.x + side*w*vehicle.right_x + fore*length*vehicle.forward_x,
                      vehicle.center.y + side*w*vehicle.right_y + fore*length*vehicle.forward_y,
                      .035 + up*height)

    def ring(half_width, rear, front, z):
        return [corner(-half_width, rear, z), corner(half_width, rear, z),
                corner(half_width, front, z), corner(-half_width, front, z)]

    def surface(points, rgb):
        renderer._draw_quad(*points, (*rgb[:3], alpha))

    def sides(lower, upper, colors):
        for i, color in enumerate(colors):
            j = (i+1) % 4
            surface((lower[i], lower[j], upper[j], upper[i]), color)

    base = ring(.44, -.46, .45, .09)
    belt = ring(.50, -.50, .50, .53)
    sill = ring(.46, -.38, .33, .54)
    roof = ring(.35, -.18, .15, .96)
    renderer._draw_vehicle_shadow(vehicle)
    sides(base, belt, (vehicle.rear_color, vehicle.side_color, vehicle.body_color, vehicle.side_color))
    surface(belt, vehicle.body_color)
    sides(sill, roof, ((59, 80, 99), (86, 106, 120), (70, 91, 110), (86, 106, 120)))
    surface(roof, (209, 218, 225))
