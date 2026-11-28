"""Optional standalone Mac HUD layer; install after standard HUD overlays.
No control paths or vehicle Params modified. Stop Jetlink before applying.
"""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = "openpilot/selfdrive/carrot/cluster/"
PIN = "a564ce1dc082909b1fdc73b72e64d920336b34d6"
PARSE = '''    lane_text, lane_deadline = "", 0.0
    lane_info = _get(data, "amapLaneCandidate")
    if status is not None and status.guidance_active and not status.off_route and bool(_get(lane_info, "valid", False)):
        deadline = _int(lane_info, "deadlineMonoTimeNanos") / 1e9
        raw = _text(lane_info, "fieldsJson")
        if 0 < deadline - now <= 2.0 and 0 < len(raw) <= 8192:
            try:
                c = json.loads(raw)
                if isinstance(c, dict) and c.get("source") in ("amap_auto_13012", "amap_link_14") and c.get("control_input") is False and c.get("absolute_mapping_verified") is False:
                    count, rows = c.get("count"), c.get("lanes")
                    if type(count) is int and 1 <= count <= 32 and isinstance(rows, list) and len(rows) == count and all(
                        isinstance(r, dict) and type(r.get("index")) is int and r["index"] == i and "advised" in r and (r["advised"] is None or type(r["advised"]) is bool)
                        for i, r in enumerate(rows)
                    ):
                        lane_text = f"車道候選 {sum(r['advised'] is True for r in rows)}/{count} 未配對"
                        lane_deadline = deadline
            except (ValueError, TypeError, RecursionError):
                pass
'''
SHOW = '''    show_lane_candidate = bool(state.amap_lane_candidate_text and current is not None and status is not None and status.guidance_active and not status.off_route and 0 < state.amap_lane_candidate_deadline_s - now <= 2.0)
    if show_lane_candidate:
        deadlines.append(state.amap_lane_candidate_deadline_s)
'''
DRAW = '''        if navi is not None and getattr(navi, "amap_lane_candidate_text", "") and 0 < getattr(navi, "amap_lane_candidate_deadline_s", 0.0) - time.monotonic() <= 2.0:
            nav_heading += " · " + navi.amap_lane_candidate_text
'''
CLOCK = '''        lane = navi.amapLaneCandidate
        if lane.valid:
          deadline = int(lane.deadlineMonoTimeNanos) + offset_ns - 250000000
          if 0 < deadline <= (1 << 64) - 1:
            lane.deadlineMonoTimeNanos = deadline
          else:
            lane.valid = False
            lane.deadlineMonoTimeNanos = 0
            lane.fieldsJson = ''
'''
# The old installer assumed the optional exit overlay was installed.
# Match either verified baseline or the exit overlay without overwriting either.
BASE_STATUS = "\tnavigationStatus @14 :NavigationStatus;"
EXIT_FIELD = "\tamapExitInfo @15 :AmapExitInfo;"
LANE_FIELD = "\tamapLaneCandidate @16 :AmapExitInfo;"
BASE_SCHEMA = BASE_STATUS + "\n\n\tstruct ItemMeta {"
BASE_SCHEMA_LANE = BASE_STATUS + "\n" + EXIT_FIELD + " # lane-test reserved wire slot\n" + LANE_FIELD + """

\tstruct AmapExitInfo {
\t\tvalid @0 :Bool;
\t\tdeadlineMonoTimeNanos @1 :UInt64;
\t\tfieldsJson @2 :Text;
\t}

\tstruct ItemMeta {"""
# No need to depend on an earlier clock overlay for a bare helper.
BASE_CLOCK = """      if name == 'carrotNavi':
        # lane-test clock adapter
        navi = self.data[name].carrotNavi
        offset_ns = round(shift * 1e9)
        for item in (navi.vehicle, navi.guidanceCurrent, navi.guidanceNext,
                     navi.laneCurrent, *navi.laneAhead, navi.speed, navi.trafficSignal,
                     navi.crossroad, navi.route, navi.navigationStatus):
          meta = item.meta
          if meta.present and meta.receivedMonoTimeNanos > 0:
            meta.receivedMonoTimeNanos = max(1, meta.receivedMonoTimeNanos + offset_ns)
"""
def changes(root):
    def read(rel):
        return (root/rel).read_text()
    schema = read("openpilot/cereal/custom.capnp")
    models = read(ROOT+"cluster_models.py")
    navi = read(ROOT+"cluster_navi.py")
    renderer = read(ROOT+"cluster_renderer.py")
    hud = read("tools/jetlink/hud.py")
    heading = '        self._draw_text(self._ellipsize_text(nav_heading, 16.0, width), x, 14.0, 16.0, theme.muted)'
    plain = '        self._draw_text(self._text("navigation"), x, 14.0, 16.0, theme.muted)'
    if "lane-test reserved wire slot" in schema or EXIT_FIELD not in schema:
        schema_edit = (BASE_SCHEMA, BASE_SCHEMA_LANE)
    else:
        schema_edit = (EXIT_FIELD, EXIT_FIELD+"\n"+LANE_FIELD)
    model_anchor = '    amap_route_remaining_text: str = ""' if '    amap_route_remaining_text: str = ""' in models else '    status: NaviStatusInfo | None = None'
    model_edit = (model_anchor,model_anchor+'\n    amap_lane_candidate_text: str = ""\n    amap_lane_candidate_deadline_s: float = 0.0')
    if '        amap_route_remaining_text=route_remaining,' in navi:
        parse_anchor = "        amap_route_remaining_text=route_remaining,"
        fresh_anchor = '        amap_route_remaining_text=state.amap_route_remaining_text if show_exit else "",'
        show_anchor = "    if show_exit:\n        deadlines.append(state.amap_exit_deadline_s)"
        parse_edit=(parse_anchor,parse_anchor+"\n        amap_lane_candidate_text=lane_text,\n        amap_lane_candidate_deadline_s=lane_deadline,")
        fresh_edit=(fresh_anchor,fresh_anchor+'\n        amap_lane_candidate_text=state.amap_lane_candidate_text if show_lane_candidate else "",\n        amap_lane_candidate_deadline_s=state.amap_lane_candidate_deadline_s if show_lane_candidate else 0.0,')
    else:
        parse_anchor = "        status=status,\n    )\n    return fresh_carrot_navi(state, now)[0]"
        fresh_anchor = "        status=status,\n    )\n    return effective, min(deadlines, default=math.inf)"
        show_anchor = "    status = fresh(state.status, STATUS_TTL_S)"
        parse_edit=(parse_anchor,parse_anchor.replace("        status=status,","        status=status,\n        amap_lane_candidate_text=lane_text,\n        amap_lane_candidate_deadline_s=lane_deadline,"))
        fresh_edit=(fresh_anchor,fresh_anchor.replace("        status=status,",'        status=status,\n        amap_lane_candidate_text=state.amap_lane_candidate_text if show_lane_candidate else "",\n        amap_lane_candidate_deadline_s=state.amap_lane_candidate_deadline_s if show_lane_candidate else 0.0,'))
    if plain in renderer or "lane-test standalone heading" in renderer:
        draw_edit=(plain,'        nav_heading = self._text("navigation") # lane-test standalone heading\n'+DRAW+heading)
    else:
        draw_edit=(heading,DRAW+heading)
    clock_anchor="      self.generations[name] = mono\n      self.updated[name] = True"
    clock_prefix=BASE_CLOCK if "lane-test clock adapter" in hud or "offset_ns = round(shift * 1e9)" not in hud else ""
    parse_block = PARSE if "import json\n" in navi and "lane-test local json" not in navi else "    import json # lane-test local json\n"+PARSE
    return {
      "openpilot/cereal/custom.capnp":[schema_edit],
      ROOT+"cluster_models.py":[model_edit],
      ROOT+"cluster_navi.py":[("    state = NaviLiveState(",parse_block+"    state = NaviLiveState("),parse_edit,
        (show_anchor,show_anchor+"\n"+SHOW.rstrip("\n")),fresh_edit],
      ROOT+"cluster_renderer.py":[draw_edit],
      "tools/jetlink/hud.py":[(clock_anchor,clock_prefix+CLOCK+clock_anchor)],
    }
def apply(root, rollback=False):
    if subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()!=PIN:
        raise ValueError("Unexpected Mac helper revision; do not patch")
    pending={}
    for rel,edits in changes(root).items():
        p=root/rel; original=p.read_text(); text=original
        for old,new in reversed(edits) if rollback else edits:
            if rollback:
                if text.count(new)==1: text=text.replace(new,old,1)
                elif text.count(old)!=1: raise ValueError("Unexpected rollback anchor: "+rel)
            else:
                if text.count(new)==1: continue
                if text.count(old)!=1: raise ValueError("Unexpected install anchor: "+rel)
                text=text.replace(old,new,1)
        if rel.endswith(".py"):compile(text,rel,"exec")
        if text!=original:pending[p]=(original,text)
    written=[]
    try:
        for p,(old,new) in pending.items():
            tmp=p.with_suffix(p.suffix+".lane-tmp")
            tmp.write_text(new);tmp.chmod(p.stat().st_mode & 0o777);tmp.replace(p);written.append(p)
    except OSError:
        for p in written:p.write_text(pending[p][0])
        raise
    return len(written)
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("root",type=Path);a.add_argument("--rollback",action="store_true")
    args=a.parse_args()
    if sys.platform=="darwin" and subprocess.run(["pgrep","-x","Jetlink"],stdout=subprocess.DEVNULL).returncode==0:
        raise SystemExit("Exit Jetlink before changing HUD helper")
    print("Files changed:",apply(args.root,args.rollback))
