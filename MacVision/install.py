from pathlib import Path
import shutil
import sys

dest = Path(sys.argv[1])
path = dest / "cluster_renderer.py"
src = path.read_text()
anchor = '            self._profile_add("draw_scene.vehicles", profile_stage)\n'
hook = ("            from mac_vision_overlay import draw as draw_mac_vision\n"
        "            draw_mac_vision(self, state, scene.scene_shift_x_m, EGO_FORWARD_M)\n")
footer = '        self._profile_add("hud.git_status", profile_stage)\n'
notice = ("        from mac_vision_overlay import draw_crosswalk_notice\n"
          "        draw_crosswalk_notice()\n")
if src.count(anchor) != 1 or src.count(footer) != 1:
    sys.exit("Unsupported renderer layout. No files changed.")
remove = "--remove" in sys.argv
updated = src.replace(anchor+hook, anchor).replace(footer+notice, footer)
if not remove:
    shutil.copyfile(Path(__file__).with_name("mac_vision_overlay.py"), dest / "mac_vision_overlay.py")
    updated = updated.replace(anchor, anchor+hook).replace(footer, footer+notice)
if updated != src:
    compile(updated, str(path), "exec")
    tmp = path.with_suffix(".vision.tmp")
    tmp.write_text(updated)
    shutil.copymode(path,tmp)
    tmp.replace(path)
