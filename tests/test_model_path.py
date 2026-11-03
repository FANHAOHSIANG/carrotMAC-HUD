import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import install_model_path as installer


class ModelPathTests(unittest.TestCase):
    def test_preserves_exact_model_state_without_projecting_map(self):
        source = '''class HUD:
    def _with_external_nav_route(self, state):
        raise AssertionError("old map replacement")
    def map_panel(self):
        return "map untouched"
'''
        patched = installer.patch_live(source)
        self.assertEqual(installer.patch_live(patched), patched)
        scope = {'ClusterUiState': object}
        exec(patched, scope)
        hud = scope['HUD']()
        for state in [SimpleNamespace(model_path=(), valid=False),
                      SimpleNamespace(model_path=((0, 0), (30, 1)), valid=True)]:
            self.assertIs(hud._with_external_nav_route(state), state)
        self.assertEqual(hud.map_panel(), 'map untouched')

    def test_unknown_helper_is_rejected(self):
        with self.assertRaises(ValueError):
            installer.patch_live('class Unknown: pass')
