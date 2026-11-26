"""Place Mac Vision pictograms in the HUD driving panel."""
import pyray as rl

from hud_object_icons import ICON_COLORS, draw_object_icon


def draw_class_icons(anchors, bounds, size, metric_rects=()):
    """Keep each pictogram beside its observed target, including nearby targets."""
    left, top, right, bottom = bounds
    if min(right - left, bottom - top) < size:
        return 0
    half = size / 2
    centers = []
    placements = []
    offsets = ((-.63, -.72), (.63, -.72), (0., -1.84), (-1.26, -1.84), (1.26, -1.84),
               (-1.84, -.72), (1.84, -.72), (-.63, .49), (.63, .49), (-1.84, .49),
               (1.84, .49), (0., 1.65), (-1.26, 1.65), (1.26, 1.65))
    if metric_rects:
        offsets += ((0., 2.75), (0., -2.9), (-2.85, 0.), (2.85, 0.))
    for kind, x, y in anchors:
        if not (left <= x < right and top <= y < bottom):
            continue
        for dx, dy in offsets:
            cx = min(max(x + size * dx, left + half), right - half)
            cy = min(max(y + size * dy, top + half), bottom - half)
            if any(cx + half + 2 > rx and cx - half - 2 < rx + rw and
                   cy + half + 2 > ry and cy - half - 2 < ry + rh for rx, ry, rw, rh in metric_rects):
                continue
            if all(abs(cx - px) >= size + 1 or abs(cy - py) >= size + 1 for px, py in centers):
                centers.append((cx, cy))
                placements.append((kind, x, y, cx, cy))
                break

    # Draw every leader before painting the icons so lines never cross a glyph.
    for kind, x, y, cx, cy in placements:
        # The anchor itself can lie inside a speed label. Omit a connector
        # across its text while retaining the class icon beside the vehicle.
        if any(max(x, cx) + 2 > rx and min(x, cx) - 2 < rx + rw and
               max(y, cy) + 2 > ry and min(y, cy) - 2 < ry + rh for rx, ry, rw, rh in metric_rects):
            continue
        start, end = rl.Vector2(x, y), rl.Vector2(cx, cy)
        rl.draw_line_ex(start, end, max(2., size * .11), rl.Color(20, 30, 40, 245))
        rl.draw_line_ex(start, end, max(1., size * .048), rl.Color(*ICON_COLORS[kind]))
    for kind, _, _, cx, cy in placements:
        draw_object_icon(kind, cx, cy, size)
    return len(placements)
