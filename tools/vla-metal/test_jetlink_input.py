import json
from pathlib import Path
import struct
import tempfile
import unittest
from types import SimpleNamespace as N
from jetlink_input import read_packet, healthy, compare

class JetlinkInputTests(unittest.TestCase):
    def test_packet_and_stale_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'snapshot.packet'
            obj={'version':1,'sent':10.,'events':{},'valid':{},'alive':{},'cameras':{}}
            p.write_bytes(struct.pack('<d',100.)+json.dumps(obj).encode())
            self.assertEqual(read_packet(p,100.1)[1],obj)
            for now in (99.9,100.5,101):
                with self.assertRaises(ValueError):
                    read_packet(p,now)

    def test_primary_guard(self):
        m=N(visionCompute='nonUsb',visionCameraInputs='roadWide',timestampEof=1_000_000_000,
            frameAge=0,frameDropPerc=0.,modelExecutionTime=.041,
            action=N(desiredAcceleration=0.,desiredCurvature=0.,shouldStop=False))
        d=N(thermalStatus='green',memoryUsagePercent=50)
        self.assertTrue(healthy(m,1_080_000_000,d,'MAC'))
        self.assertFalse(healthy(m,1_150_000_000,d,'MAC'))
        self.assertFalse(healthy(m,1_080_000_000,d,'jetSON'))
        m.modelExecutionTime=.05
        self.assertFalse(healthy(m,1_080_000_000,d,'MAC'))

    def test_stop_comparison(self):
        self.assertEqual(compare({'should_stop':True},{'longitudinal':'stop'}),'both_stop')
        self.assertEqual(compare({'should_stop':False},{'longitudinal':'stop'}),'vla_only_stop')
        self.assertEqual(compare({'should_stop':True},{'longitudinal':None}),'unknown')

if __name__=='__main__':
    unittest.main()
