from pathlib import Path
import subprocess
import shutil
import sys
from tempfile import TemporaryDirectory

dest = Path(sys.argv[1])
path = dest / "cluster_renderer.py"
src = path.read_text()
anchor = '            self._profile_add("draw_scene.vehicles", profile_stage)\n'
hook = ("            from mac_vision_overlay import draw as draw_mac_vision\n"
        "            draw_mac_vision(self, state, scene.scene_shift_x_m, EGO_FORWARD_M)\n")
footer = '        self._profile_add("hud.git_status", profile_stage)\n'
notice = ("        from mac_vision_overlay import draw_crosswalk_notice\n"
          "        draw_crosswalk_notice()\n")
vehicle_loop = "            for vehicle in scene.vehicles:\n"
ioniq_loop = """            if scene.vehicles:
                from ioniq5_model import draw as draw_ioniq5
                self._draw_vehicle_shadow(scene.vehicles[0])
                draw_ioniq5(scene.vehicles[0])
            for vehicle in scene.vehicles[1:]:
"""
if src.count(vehicle_loop) + src.count(ioniq_loop) != 1:
    sys.exit("Unsupported ego vehicle layout. No files changed.")
if src.count(anchor) != 1 or src.count(footer) != 1:
    sys.exit("Unsupported renderer layout. No files changed.")
remove = "--remove" in sys.argv
# Apply the lamp layer separately so existing Vision installations can upgrade.
patch = Path(__file__).with_name("ego-lamps.patch").resolve()
git_apply = ["git", "-C", str(dest.resolve().parents[3]), "apply"]
direction = ["--reverse"] if remove else []
opposite = [] if remove else ["--reverse"]
with TemporaryDirectory() as temporary:
    # P/R display inserts gear_valid immediately after onroad in cluster_live.
    live = (dest / "cluster_live.py").read_text()
    if "            gear_valid=gear_valid,\n" in live:
        body = patch.read_text().replace(
            "             alert=self._live_cluster_alert(state.alert, onroad),\n",
            "             gear_valid=gear_valid,\n", 1,
        )
        patch = Path(temporary) / patch.name
        patch.write_text(body)
    if subprocess.run([*git_apply, *opposite, "--check", str(patch)], capture_output=True).returncode:
        subprocess.run([*git_apply, *direction, str(patch)], check=True)
        src = path.read_text()
updated = src.replace(anchor+hook, anchor).replace(footer+notice, footer)
updated = updated.replace(ioniq_loop, vehicle_loop)
if not remove:
    shutil.copyfile(Path(__file__).with_name("ioniq5_model.py"), dest / "ioniq5_model.py")
    updated = updated.replace(vehicle_loop, ioniq_loop)
    shutil.copyfile(Path(__file__).with_name("mac_vision_overlay.py"), dest / "mac_vision_overlay.py")
    updated = updated.replace(anchor, anchor+hook).replace(footer, footer+notice)
if updated != src:
    compile(updated, str(path), "exec")
    tmp = path.with_suffix(".vision.tmp")
    tmp.write_text(updated)
    shutil.copymode(path,tmp)
    tmp.replace(path)
