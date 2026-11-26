import unittest

from vision import RoadDetections


class RoadDetectionsTest(unittest.TestCase):
    def setUp(self):
        self.road = RoadDetections()
        self.bike = ["motorcycle", .5, .8, .14, .21]
        self.rider = ["person", .50, .73, .07, .25]
        self.walker = ["person", .625, .81, .07, .25]
        self.car = ["car", .50, .80, .14, .22]

    def test_one_rider_bike_and_neighbor(self):
        objects = self.road.resolve([(self.rider,.8), (self.walker,.8), (self.bike,.7)], 1.)
        self.assertEqual(objects, [self.walker, self.bike])

    def test_repeated_weaker_motorcycle_detection(self):
        items = [(self.rider,.8), (self.bike,.38)]
        self.assertEqual(self.road.resolve(items, 1.), [self.rider])
        self.assertEqual(self.road.resolve(items, 1.2), [self.bike])
        self.assertEqual(self.road.resolve(items, 2.), [self.rider])

    def test_car_disagreement_requires_two_bike_frames_and_predominant_score(self):
        pair = [(self.car,.6),(self.bike,.68)]
        self.assertEqual(len(self.road.resolve(pair, 1.)), 2)
        self.assertEqual(self.road.resolve(pair, 1.2), [self.bike])
        self.assertEqual(len(self.road.resolve([(self.car,.9),(self.bike,.6)], 1.4)), 2)

    def test_ambiguous_pair_and_lost_bike(self):
        pedestrian = ["person",.51,.74,.05,.26]
        self.assertEqual(len(self.road.resolve([(pedestrian,.8),(self.rider,.8),(self.bike,.8)], 1.)), 3)
        self.assertEqual(self.road.resolve([(self.rider,.8)], 1.2), [self.rider])
        self.assertEqual(self.road.resolve([], 1.4), [])
