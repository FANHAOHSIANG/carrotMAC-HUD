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

if __name__ == "__main__":
    unittest.main()
