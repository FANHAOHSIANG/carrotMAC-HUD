import json, sys, unittest
from pathlib import Path
root=Path(sys.argv.pop(1))
sys.path.insert(0,str(root/'openpilot/selfdrive/carrot/cluster'))
from cluster_navi import parse_carrot_navi,fresh_carrot_navi

NOW=50.0
def sample():
    meta={"present":True,"sequence":1,"sourceTimestampMillis":1000,"receivedMonoTimeNanos":49500000000}
    return {"schemaVersion":1,"connected":True,"sessionId":"test","guidanceCurrent":{"meta":meta,"distanceM":800,"turnType":51},
            "navigationStatus":{"meta":meta,"guidanceActive":True,"offRoute":False},
            "amapExitInfo":{"valid":True,"deadlineMonoTimeNanos":51000000000,"fieldsJson":json.dumps({"EXIT_NAME_INFO":"竹北交流道"})}}
class ExitTests(unittest.TestCase):
    def test_fresh_and_expire(self):
        a=parse_carrot_navi(sample(),NOW)
        self.assertEqual(a.amap_exit_name,"竹北交流道")
        self.assertEqual(a.current.distance_m,800)
        self.assertEqual(fresh_carrot_navi(a,51.0)[0].amap_exit_name,"")
    def test_legacy(self):
        a=sample(); del a["amapExitInfo"]
        self.assertEqual(parse_carrot_navi(a,NOW).amap_exit_name,"")
    def test_bad_inputs(self):
        for mod in ("invalid","offroute","stopped","expired","future","invalid_json"):
            a=sample()
            if mod=="invalid":a["amapExitInfo"]["valid"]=False
            if mod=="offroute":a["navigationStatus"]["offRoute"]=True
            if mod=="stopped":a["navigationStatus"]["guidanceActive"]=False
            if mod=="expired":a["amapExitInfo"]["deadlineMonoTimeNanos"]=49000000000
            if mod=="future":a["amapExitInfo"]["deadlineMonoTimeNanos"]=54000000000
            if mod=="invalid_json":a["amapExitInfo"]["fieldsJson"]="{"
            with self.subTest(mod=mod):self.assertEqual(parse_carrot_navi(a,NOW).amap_exit_name,"")
    def test_capnp(self):
        import capnp
        p=root/'openpilot/cereal'
        schema=capnp.load(str(p/'custom.capnp'),imports=[str(p)])
        a=sample()
        msg=schema.CarrotNaviState.new_message(**a)
        with schema.CarrotNaviState.from_bytes(msg.to_bytes()) as v:
            self.assertEqual(parse_carrot_navi(v,NOW).amap_exit_name,"竹北交流道")
if __name__=='__main__':unittest.main()
