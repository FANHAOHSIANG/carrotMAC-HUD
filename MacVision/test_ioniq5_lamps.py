import itertools
import unittest

from ioniq5_model import EGO_MESH_SCALE, lamp_geometry


class Ioniq5LampsTest(unittest.TestCase):
    def test_active_banks_match_each_signal_combination(self):
        for style, pixels in (("factory", 4), ("night", 3), ("large", 2)):
            for brake, left, right in itertools.product((False, True), repeat=3):
                with self.subTest(style=style, brake=brake, left=left, right=right):
                    faces = lamp_geometry(style, brake, left, right)
                    stops = [vertices for color, vertices in faces if color == (255, 42, 45)]
                    turns = [vertices for color, vertices in faces if color == (255, 186, 35)]
                    strip = [vertices for color, vertices in faces if color == (255, 56, 52)]
                    self.assertEqual(len(strip), int(brake))
                    for side, active in ((-1, left), (1, right)):
                        self.assertEqual(sum(all(side * x > 0 for x, _, _ in bank) for bank in stops),
                                         pixels if brake else 0)
                        self.assertEqual(sum(all(side * x > 0 for x, _, _ in bank) for bank in turns),
                                         pixels if active else 0)

    def test_lens_size_and_separation_after_mesh_scaling(self):
        # Lengths are fractions of the original ego box after the mesh scale.
        for style in ("factory", "night", "large"):
            with self.subTest(style=style):
                faces = lamp_geometry(style, True, True, True)
                for color, min_height in (((255, 42, 45), .13), ((255, 186, 35), .095)):
                    lenses = [vertices for tint, vertices in faces if tint == color and vertices[0][0] > 0]
                    points = [point for lens in lenses for point in lens]
                    width = max(x for x, _, _ in points) - min(x for x, _, _ in points)
                    self.assertGreaterEqual(width * EGO_MESH_SCALE, .30)
                    for lens in lenses:
                        height = max(z for _, _, z in lens) - min(z for _, _, z in lens)
                        self.assertGreaterEqual(height * EGO_MESH_SCALE, min_height)
                red_bottom = min(z for tint, points in faces if tint == (255, 42, 45) for _, _, z in points)
                amber_top = max(z for tint, points in faces if tint == (255, 186, 35) for _, _, z in points)
                self.assertGreaterEqual((red_bottom - amber_top) * EGO_MESH_SCALE, .02)
