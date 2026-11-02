import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import install_blue_line as installer
spec = importlib.util.spec_from_file_location('nav_line', ROOT / 'overlays/nav-preview/cluster_nav_line.py')
line = importlib.util.module_from_spec(spec)
spec.loader.exec_module(line)


class BlueLineTests(unittest.TestCase):
    def setUp(self):
        self.scale = 40008000. / 360.
        self.route = tuple((x / self.scale, 3 / self.scale) for x in [-10, 10, 50, 100])

    def test_near_plane_preserves_lateral_offset(self):
        points = line.project_route(self.route, (0, 0, 0))
        self.assertEqual(points[0], (0, 3))
        self.assertTrue(all(abs(y - 3) < 1e-8 for x, y in points))
        self.assertTrue(all(b[0] - a[0] == 2 for a, b in zip(points, points[1:])))

    def test_invalid_and_backward_routes_do_not_bridge(self):
        self.assertEqual(line.project_route(self.route, None), ())
        self.assertEqual(line.project_route(tuple(reversed(self.route)), (0, 0, 0)), ())
        self.assertEqual(line.project_route(self.route, (float('nan'), 0, 0)), ())

    def test_interpolation_reduces_step_and_converges(self):
        f = line.DisplayRoute()
        first = dict(f.update(self.route, (0, 0, 0), 1))[30]
        anchor = (0, 1 / self.scale, 0)
        target = dict(line.project_route(self.route, anchor))[30]
        second = dict(f.update(self.route, anchor, 1.05))[30]
        self.assertLess(abs(second - first), abs(target - first))
        for n in range(1, 40):
            last = dict(f.update(self.route, anchor, 1.05 + n * .05))[30]
        self.assertAlmostEqual(last, target, places=5)

    def test_disconnect_gap_route_and_turn_reset(self):
        for kind in ['gap', 'route', 'turn', 'disconnect']:
            with self.subTest(kind=kind):
                f = line.DisplayRoute()
                f.update(self.route, (0, 0, 0), 1)
                route, anchor, now = self.route, (0, 1 / self.scale, 0), 1.05
                if kind == 'gap': now = 2
                if kind == 'route': route = self.route + ((120 / self.scale, 3 / self.scale),)
                if kind == 'turn': anchor = (0, 0, 20)
                if kind == 'disconnect': f.update(self.route, None, 1.02)
                self.assertEqual(f.update(route, anchor, now), line.project_route(route, anchor))

    def test_actual_projection_patch_is_idempotent(self):
        source = '''class HUD:
    def _external_nav_route_model_path(self):
        anchor = self._nav_route_anchor_from_carrot_man()
        return self._nav_route_coords
'''
        patched = installer.patch_live(source)
        self.assertEqual(installer.patch_live(patched), patched)
        self.assertIn('DisplayRoute', patched)
        with self.assertRaises(ValueError):
            installer.patch_live('class Unknown: pass')


if __name__ == '__main__':
    unittest.main()
