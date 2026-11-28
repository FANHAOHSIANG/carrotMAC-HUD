"""Reversible neutral lane observation strip; requires stopped HUD."""
from pathlib import Path
import argparse
import subprocess
import sys
from apply_lane_candidate import apply, PIN

EDITS = {
  "openpilot/selfdrive/carrot/cluster/cluster_models.py": [
    [
      "    amap_lane_candidate_text: str = \"\"",
      "    amap_lane_candidate_text: str = \"\"\n    amap_lane_candidate_codes: tuple[str, ...] = ()"
    ]
  ],
  "openpilot/selfdrive/carrot/cluster/cluster_navi.py": [
    [
      "    lane_text, lane_deadline = \"\", 0.0",
      "    lane_text, lane_deadline = \"\", 0.0\n    lane_codes = ()"
    ],
    [
      "                        lane_deadline = deadline",
      "                        lane_deadline = deadline\n                        if count <= 8 and all(type(r.get(\"back_code\")) is int and 0 <= r[\"back_code\"] <= 65535 for r in rows):\n                            lane_codes = tuple(str(r[\"back_code\"]) + (\"*\" if r[\"advised\"] is True else \"?\" if r[\"advised\"] is None else \"\") for r in rows)"
    ],
    [
      "        amap_lane_candidate_text=lane_text,",
      "        amap_lane_candidate_text=lane_text,\n        amap_lane_candidate_codes=lane_codes,"
    ],
    [
      "        amap_lane_candidate_text=state.amap_lane_candidate_text if show_lane_candidate else \"\",",
      "        amap_lane_candidate_text=state.amap_lane_candidate_text if show_lane_candidate else \"\",\n        amap_lane_candidate_codes=state.amap_lane_candidate_codes if show_lane_candidate else (),"
    ]
  ],
  "openpilot/selfdrive/carrot/cluster/cluster_renderer.py": [
    [
      "            self._profile_add(\"hud.center_clock\", profile_stage)\n        finally:",
      "            self._profile_add(\"hud.center_clock\", profile_stage)\n            self._draw_amap_lane_observation(state, screen_mode)\n        finally:"
    ],
    [
      "    def _effective_screen_mode(",
      "    def _draw_amap_lane_observation(self, state: ClusterUiState, screen_mode: int) -> None:\n        # Neutral provider codes, not arrows or spatial lane assignments.\n        navi = getattr(state, \"navi_live\", None)\n        if navi is None or not getattr(navi, \"amap_lane_candidate_text\", \"\"):\n            return\n        if not 0 < getattr(navi, \"amap_lane_candidate_deadline_s\", 0.0) - time.monotonic() <= 2.0:\n            return\n        codes = getattr(navi, \"amap_lane_candidate_codes\", ())\n        if not codes or len(codes) > 8:\n            return\n        center = (DESIGN_WIDTH if screen_mode == CLUSTER_SCREEN_MODE_FULLSCREEN_3D else CAMERA_BACKGROUND_W) * 0.5\n        label = \"MAP OBS  \" + \" | \".join(codes)\n        # Small neutral strip below top widgets. No direction or lane-selection color.\n        self._draw_text_with_stroke(label, center, 98.0, 19.0, self._current_theme().muted, (10, 13, 16), 2, anchor=\"center\")\n\n    def _effective_screen_mode("
    ],
    [
      "            nav_heading += \" · \" + navi.amap_lane_candidate_text",
      "            nav_heading += \" · MAP OBS \" + \" | \".join(getattr(navi, \"amap_lane_candidate_codes\", ())) if getattr(navi, \"amap_lane_candidate_codes\", ()) else \" · \" + navi.amap_lane_candidate_text"
    ]
  ]
}

def patch(root, rollback=False):
    if subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()!=PIN:
        raise ValueError("Unexpected Mac helper revision")
    pending={}
    for rel,pairs in EDITS.items():
        p=root/rel
        original=p.read_text()
        s=original
        for old,new in reversed(pairs) if rollback else pairs:
            if rollback:
                if s.count(new)==1: s=s.replace(new,old,1)
                elif s.count(old)!=1: raise ValueError("Unexpected rollback anchor: "+rel)
            else:
                if s.count(new)==1: continue
                if s.count(old)!=1: raise ValueError("Unexpected strip anchor: "+rel)
                s=s.replace(old,new,1)
        compile(s,rel,"exec")
        if s!=original:pending[p]=(original,s)
    written=[]
    try:
        for p,(old,new) in pending.items():
            tmp=p.with_suffix(p.suffix+".lane-strip-tmp")
            tmp.write_text(new)
            tmp.chmod(p.stat().st_mode & 0o777)
            tmp.replace(p)
            written.append(p)
    except OSError:
        for p in written:p.write_text(pending[p][0])
        raise
    return len(written)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    parser.add_argument("--rollback",action="store_true")
    a=parser.parse_args()
    if sys.platform=="darwin" and subprocess.run(["pgrep","-x","Jetlink"],stdout=subprocess.DEVNULL).returncode==0:
        raise SystemExit("Exit Jetlink before changing HUD helper")
    if not a.rollback:
        # Apply base only if missing; the previous installer expects its own exact blocks.
        if "amap_lane_candidate_text" not in (a.root/"openpilot/selfdrive/carrot/cluster/cluster_models.py").read_text():
            apply(a.root)
    print("Lane strip files changed:",patch(a.root,a.rollback))
