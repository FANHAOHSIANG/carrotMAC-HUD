import json, sys, unittest
from pathlib import Path
root=Path(sys.argv.pop(1))
sys.path.insert(0,str(root/'openpilot/selfdrive/carrot/cluster'))
from cluster_navi import parse_carrot_navi, fresh_carrot_navi
def sample():
    meta={"present":True,"sequence":1,"sourceTimestampMillis":1000,"receivedMonoTimeNanos":49500000000}
    c={"source":"amap_link_14","count":2,"lanes":[{"index":0,"advised":False},{"index":1,"advised":True}],"control_input":False,"absolute_mapping_verified":False}
    return {"schemaVersion":1,"connected":True,"sessionId":"test","guidanceCurrent":{"meta":meta,"distanceM":800,"turnType":51},"navigationStatus":{"meta":meta,"guidanceActive":True,"offRoute":False},"amapLaneCandidate":{"valid":True,"deadlineMonoTimeNanos":51000000000,"fieldsJson":json.dumps(c)}}
class Checks(unittest.TestCase):
    def test_live(self):
        s=sample();a=parse_carrot_navi(s,50.)
        self.assertEqual(a.amap_lane_candidate_text,"車道候選 1/2 未配對")
        self.assertEqual(fresh_carrot_navi(a,51.)[0].amap_lane_candidate_text,"")
    def test_offroute(self):
        s=sample();s["navigationStatus"]["offRoute"]=True
        self.assertEqual(parse_carrot_navi(s,50.).amap_lane_candidate_text,"")
    def test_legacy(self):
        s=sample();del s["amapLaneCandidate"]
        self.assertEqual(parse_carrot_navi(s,50.).amap_lane_candidate_text,"")
    def test_capnp(self):
        import capnp
        p=root/'openpilot/cereal'
        schema=capnp.load(str(p/'custom.capnp'),imports=[str(p)])
        with schema.CarrotNaviState.from_bytes(schema.CarrotNaviState.new_message(**sample()).to_bytes()) as v:
            self.assertEqual(parse_carrot_navi(v,50.).amap_lane_candidate_text,"車道候選 1/2 未配對")
if __name__=="__main__":unittest.main()
