"""Install or remove Mac Vision and the Mac-only HUD appearance controls."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory

SRC = Path(__file__).resolve().parent
REL = Path("openpilot/selfdrive/carrot/cluster")
FILES = ("cluster_models.py", "cluster_live.py", "cluster_renderer.py")
MODULES = ("hud_style.py", "ioniq5_model.py", "mac_vision_overlay.py", "hud_road_edges.py")
LOOP = "            for vehicle in scene.vehicles:\n"
LEGACY_MODEL_LOOP = """            if scene.vehicles:
                from ioniq5_model import draw as draw_ioniq5
                self._draw_vehicle_shadow(scene.vehicles[0])
                draw_ioniq5(scene.vehicles[0])
            for vehicle in scene.vehicles[1:]:
"""
MODEL_LOOP = LEGACY_MODEL_LOOP.replace(
    "            for vehicle in scene.vehicles[1:]:\n",
    "            from mac_vision_overlay import draw as draw_mac_vision\n"
    "            drawn_bikes = draw_mac_vision(self, state, scene.scene_shift_x_m, EGO_FORWARD_M, scene.vehicles[1:])\n"
    "            for index, vehicle in enumerate(scene.vehicles[1:]):\n"
    "                if index in drawn_bikes:\n                    continue\n")
OLD_LAMPS = "                    self._draw_ego_lamps(scene.vehicles[0], brake, left, right)"
NEW_LAMPS = """                    from ioniq5_model import draw_lamps
                    draw_lamps(scene.vehicles[0], brake, left, right)"""
ARROWS = "        if not lit and not show_inactive:\n"
LIMIT = "        if state.speed_limit_kph is not None or state.navi_debug is not None:\n"
ROAD_EDGE_HOOKS = (
    ('cluster_models.py', '    left_road_edge_offset: float | None = None\n',
     '    road_edge_filter_active: bool = False\n'),
    ('cluster_live.py', '        return replace(\n            state,\n            onroad=onroad,\n',
     '        from hud_road_edges import filter_live_targets\n        if self._service_alive("modelV2") and self._service_valid("modelV2"):\n            state = filter_live_targets(state, self._service_receive_time("modelV2"), now)\n'),
)
HOOKS = (
    (LOOP, MODEL_LOOP),
    ("LEAD_ONE_DISTANCE_FONT_SIZE = 24\n", "LEAD_ONE_DISTANCE_FONT_SIZE = 28\n"),
    ("LEAD_ONE_SPEED_FONT_SIZE = 22\n", "LEAD_ONE_SPEED_FONT_SIZE = 26\n"),
    ("            lead = replace(lead, lines=tuple(",
     "            lead = replace(lead, color=(255, 94, 94), lines=tuple("),
    ('        self._draw_vehicle_box(marker_vehicle)\n',
     '        if vehicle.source.startswith("modelV2") or vehicle.source == "radarState":\n'
     '            from mac_vision_overlay import draw_native_car\n'
     '            draw_native_car(self, vehicle, Vec3)\n'
     '        else:\n'
     '            self._draw_vehicle_box(marker_vehicle)\n'),
    ('        self._profile_add("hud.git_status", profile_stage)\n',
     '        self._profile_add("hud.git_status", profile_stage)\n'
     '        from mac_vision_overlay import draw_detection_notice\n'
     '        draw_detection_notice(offset_x)\n'),
    (ARROWS, '        from hud_style import SHOW_ARROWS\n'
     '        if not SHOW_ARROWS:\n            return\n' + ARROWS),
    (LIMIT, '        from hud_style import SHOW_LIMIT\n'
     '        if SHOW_LIMIT and (state.speed_limit_kph is not None or state.navi_debug is not None):\n'),
    (OLD_LAMPS, NEW_LAMPS),
)


def write_file(path, data):
    if path.exists() and path.read_bytes() == data:
        return
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(data)
    new = Path(temp.name)
    if path.exists():
        shutil.copymode(path, new)
    new.replace(path)


def install(dest, remove):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        stage = root / REL
        stage.mkdir(parents=True)
        for name in FILES:
            shutil.copyfile(dest / name, stage / name)
        renderer = stage / "cluster_renderer.py"
        source = renderer.read_text().replace(
            '        from mac_vision_overlay import draw_crosswalk_notice\n'
            '        draw_crosswalk_notice()\n', '')
        # Normalize the previous release's overlay call for upgrade and removal.
        source = source.replace("draw_mac_vision(self, state, scene.scene_shift_x_m, EGO_FORWARD_M)",
                                "draw_mac_vision(self, state, scene.scene_shift_x_m, EGO_FORWARD_M, scene.vehicles[1:])")
        source = source.replace(LEGACY_MODEL_LOOP, LOOP).replace(
            '            from mac_vision_overlay import draw as draw_mac_vision\n'
            '            draw_mac_vision(self, state, scene.scene_shift_x_m, EGO_FORWARD_M, scene.vehicles[1:])\n', '')
        for before, after in HOOKS:
            source = source.replace(after, before)
        renderer.write_text(source)
        patch = (SRC / "ego-lamps.patch").read_text()
        if "            gear_valid=gear_valid,\n" in (stage / "cluster_live.py").read_text():
            patch = patch.replace('             alert=self._live_cluster_alert(state.alert, onroad),\n',
                                  '             gear_valid=gear_valid,\n', 1)
        patch_path = root / "lamps.patch"
        patch_path.write_text(patch)
        cmd = ["git", "apply"]
        opposite = [] if remove else ["--reverse"]
        if subprocess.run(cmd + opposite + ["--check", str(patch_path)], cwd=root,
                          capture_output=True).returncode:
            direction = ["--reverse"] if remove else []
            subprocess.run(cmd + direction + [str(patch_path)], cwd=root, check=True)
        for name, anchor, addition in ROAD_EDGE_HOOKS:
            path = stage / name
            data = path.read_text().replace(addition + anchor, anchor)
            if not remove:
                if data.count(anchor) != 1:
                    raise ValueError("HUD road-edge hook missing in " + name)
                data = data.replace(anchor, addition + anchor)
            path.write_text(data)
        source = renderer.read_text()
        writes = {}
        if not remove:
            for before, after in HOOKS:
                if source.count(before) != 1:
                    raise ValueError("HUD 版本不符，找不到唯一的繪圖位置：" + before.strip())
                source = source.replace(before, after)
            for name in MODULES:
                writes[name] = (SRC / name).read_bytes()
        renderer.write_text(source)
        for name in FILES:
            writes[name] = (stage / name).read_bytes()
        for name, data in writes.items():
            compile(data, name, "exec")
        for name, data in writes.items():
            write_file(dest / name, data)


if __name__ == "__main__":
    install(Path(sys.argv[1]), "--remove" in sys.argv[2:])
