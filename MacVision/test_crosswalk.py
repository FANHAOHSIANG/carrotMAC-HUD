import unittest
from crosswalk import best_box

class CrosswalkTest(unittest.TestCase):
    def test_padding_and_class_filter(self):
        light = [160,160,100,100,.99,.01,.95,.02]
        zebra = [160,150,160,80,.8,.9,.05,.05]
        self.assertEqual(best_box([light],320,200,0,60),[])
        box, = best_box([light,zebra],320,200,0,60)
        self.assertEqual(box[:2],["crosswalk",.5])
        self.assertAlmostEqual(box[2],.65)
        self.assertEqual(best_box([[160,10,80,8,.9,.9,0,0]],320,200,0,60),[])
