import unittest
from replay import decode, prompts, select_metal

class ReplayTests(unittest.TestCase):
    def test_metal_detection(self):
        self.assertEqual(select_metal("Available devices:\n  MTL0: Apple M4 (10000 MiB)"), ("MTL0", "Apple M4 (10000 MiB)"))
        self.assertEqual(select_metal("  Metal: Apple GPU", "Metal"), ("Metal", "Apple GPU"))
    def test_no_fallback(self):
        for listing, requested in [(" CPU: CPU", None), (" Vulkan0: GPU", None), (" MTL0: Apple M4", "CPU"), (" MTL0: A\n MTL1: B", None)]:
            with self.assertRaises(ValueError):
                select_metal(listing, requested)
    def test_prompt_and_pose(self):
        _, tails = prompts([[-i,0,0] for i in range(8,-1,-1)])
        self.assertEqual(len(tails), 3)
        self.assertTrue(all(t.count("<wp>") == 9 for t in tails))
        with self.assertRaises(ValueError):
            prompts([[0,0,0]]*8)
        with self.assertRaises(ValueError):
            prompts([[0,0,0]]*8 + [[1,0,0]])
    def test_abstain(self):
        self.assertEqual(decode(["track","turn","right"]), {"longitudinal":"cruise","lateral":"turn right"})
        self.assertEqual(decode(["?","turn","straight"]), {"longitudinal":None,"lateral":None})


class QCameraTests(unittest.TestCase):
    def test_nonzero_first_encoder_index(self):
        from types import SimpleNamespace as NS
        from export_segment import qcamera_positions
        def event(i):
            return NS(which=lambda: 'qRoadEncodeIdx', qRoadEncodeIdx=NS(
                type='qcameraH264', segmentNum=7, segmentId=12+i, frameId=100+i, timestampEof=1000+50*i))
        self.assertEqual(qcamera_positions([event(0),event(1)]), {(100,1000):0,(101,1050):1})
        with self.assertRaises(ValueError):
            qcamera_positions([event(0),event(2)])
        with self.assertRaises(ValueError):
            qcamera_positions([event(0),event(0)])
        with self.assertRaises(ValueError):
            qcamera_positions([])

    def test_manifest_prefers_original_else_preview(self):
        from download_route import choose
        base='https://example.com/routes/car/route--0:2'
        def segment(i, camera):
            return {'index':i,'files':[{'name':n,'size':10,'url':f'{base}/files/device/route/{i}/{n}'} for n in ('rlog.zst',camera)]}
        q=segment(0,'qcamera.ts')
        f=segment(1,'fcamera.hevc')
        self.assertEqual(choose({'ok':True,'segments':[q]},base)[0][1][1]['name'],'qcamera.ts')
        self.assertEqual(choose({'ok':True,'segments':[q,f]},base)[0][0],1)
        q['files'][1]['url']='https://other.example/qcamera.ts'
        with self.assertRaises(ValueError):
            choose({'ok':True,'segments':[q]},base)

if __name__ == "__main__":
    unittest.main()
