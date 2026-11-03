"""Display-only route projection. Never used by navigation or steering control."""
import math
import time


class DisplayRoute:
    """Short visual interpolation only; never feeds vehicle control."""
    def __init__(self):
        self.route = None
        self.previous = ()
        self.stamp = None
        self.heading = None

    def update(self, coords, anchor, now=None):
        now = time.monotonic() if now is None else now
        raw = project_route(coords, anchor)
        dt = now - self.stamp if self.stamp is not None else 0.
        turn = abs((anchor[2] - self.heading + 180.) % 360. - 180.) if anchor is not None and self.heading is not None else 180.
        if raw and self.route == coords and 0. < dt < .5 and turn < 15.:
            previous = dict(self.previous)
            alpha = 1. - math.exp(-dt / .12)
            raw = tuple((x, previous[x] + alpha * (y - previous[x])) if x in previous else (x, y)
                        for x, y in raw)
        self.route = tuple(coords)
        self.previous = raw
        self.stamp = now
        self.heading = anchor[2] if anchor is not None else None
        return raw


def project_route(coords, anchor):
    """Clip contiguous route segments and sample at fixed forward distances.

    Do not invent a segment from the car's origin to the first map vertex.
    Preserve the route's lateral offset, including at the near-plane crossing.
    """
    if anchor is None or len(coords) < 2:
        return ()
    lat0, lon0, heading = anchor
    if not all(math.isfinite(v) for v in anchor):
        return ()
    angle = math.radians(heading)
    c, s = math.cos(angle), math.sin(angle)
    scale = 40008000. / 360.
    longitude_scale = scale * math.cos(math.radians(lat0))
    points = []
    for lat, lon in coords:
        if not math.isfinite(lat) or not math.isfinite(lon):
            return ()
        east, north = (lon - lon0) * longitude_scale, (lat - lat0) * scale
        points.append((east * s + north * c, east * c - north * s))
    # Choose the nearest forward-facing segment, rather than accidentally
    # joining a later parallel leg of a loop or a hairpin.
    candidates = []
    for i, ((x0, y0), (x1, y1)) in enumerate(zip(points, points[1:])):
        dx, dy = x1 - x0, y1 - y0
        length2 = dx * dx + dy * dy
        if dx <= .01 or x1 < 0 or x0 > 180 or length2 <= 0:
            continue
        t = max(0., min(1., -(x0 * dx + y0 * dy) / length2))
        distance2 = (x0 + t * dx) ** 2 + (y0 + t * dy) ** 2
        candidates.append((distance2, i))
    if not candidates:
        return ()
    _, first = min(candidates)
    result = []
    next_x = None
    for (x0, y0), (x1, y1) in zip(points[first:], points[first + 1:]):
        if x1 <= x0 + .01:
            break  # End this branch; never bridge across a backwards segment.
        lo, hi = max(0., x0), min(180., x1)
        if hi < lo:
            if x0 > 180:
                break
            continue
        if next_x is None:
            next_x = math.ceil(lo / 2.) * 2.
        while next_x <= hi:
            y = y0 + (y1 - y0) * (next_x - x0) / (x1 - x0)
            if abs(y) > 40.:
                return tuple(result)
            result.append((next_x, y))
            next_x += 2.
    return tuple(result)
