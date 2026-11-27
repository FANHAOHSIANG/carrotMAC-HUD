import tempfile
import unittest
from pathlib import Path
import numpy as np
from replay import TONY_REV, OFFSETS_US, read_sample, result_xyz, score
from export_segment import choose

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"sample.npz"
        q=10_000_000
        self.data=dict(image_frames=np.zeros((10,3,432,768),np.uint8),
            camera_indices=np.array([1]*5+[6]*5),absolute_timestamps=np.tile(q+OFFSETS_US,2),
            query_us=np.int64(q),ego_history_xyz=np.zeros((1,20,3),np.float32),
            ego_history_rot=np.tile(np.eye(3,dtype=np.float32),(1,20,1,1)),
            nav_text=np.array(""),source_revision=np.array(TONY_REV))
    def read(self,**changes):
        np.savez_compressed(self.path,**{**self.data,**changes})
        return read_sample(self.path)
    def test_valid(self):
        sample,query,nav,ground=self.read()
        self.assertEqual(sample["ego_history_xyz"].shape,(1,1,20,3))
        self.assertEqual(sample["ego_history_rot"].shape,(1,1,20,3,3))
        self.assertEqual(query,10_000_000)
        self.assertIsNone(ground)
    def test_single_camera(self):
        with self.assertRaises(ValueError): self.read(camera_indices=np.ones(10,dtype=int))
    def test_future(self):
        ts=self.data["absolute_timestamps"].copy();ts[-1]+=1
        with self.assertRaises(ValueError): self.read(absolute_timestamps=ts)
    def test_repeated(self):
        ts=self.data["absolute_timestamps"].copy();ts[1]=ts[0]
        with self.assertRaises(ValueError): self.read(absolute_timestamps=ts)
    def test_invalid_pose(self):
        xyz=self.data["ego_history_xyz"].copy();xyz[0,-1,0]=1
        with self.assertRaises(ValueError): self.read(ego_history_xyz=xyz)
    def test_rotation(self):
        with self.assertRaises(ValueError): self.read(ego_history_rot=np.zeros((1,20,3,3),np.float32))
    def test_trajectory(self):
        xyz=result_xyz(np.zeros((1,1,1,64,3)))
        self.assertEqual(score(xyz,np.ones((15,3)))["max_lateral_m"],1)
        with self.assertRaises(ValueError): result_xyz(np.zeros((64,3)))
    def test_selection(self):
        q=10_000_000_000
        rows=[(q+int(off)*1000,i,q+int(off)*1000+1,i) for i,off in enumerate(OFFSETS_US)]
        self.assertEqual(choose(rows,q),rows)
        self.assertIsNone(choose(rows[1:],q))

if __name__=="__main__": unittest.main()
