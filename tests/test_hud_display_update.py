from difflib import unified_diff
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_hud_locale import CLUSTER_LIMIT_PATCH, GEAR_PATCH, RENDERER, apply_hud_patches


class HudDisplayUpdateTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.repo = root / 'renderer'
        subprocess.run(['git', 'init', '-q', self.repo], check=True)
        self.renderer = self.repo / 'renderer.py'
        self.base = 'language = "ko"\n# renderer\n\n\n\ngear_screen = False\n# switch screen\n'
        self.renderer.write_text(self.base)
        self.locale = root / 'locale.patch'
        self.locale.write_text(self.patch_text('language = "ko"', 'language = "zh-TW"'))
        self.gear = root / 'gear.patch'
        self.gear.write_text(self.patch_text('gear_screen = False', 'gear_screen = True'))
        self.patches = (self.locale, self.gear)

    def patch_text(self, old, new):
        return ''.join(unified_diff(self.base.splitlines(keepends=True),
                                    self.base.replace(old, new).splitlines(keepends=True),
                                    'a/renderer.py', 'b/renderer.py', n=1))

    def test_install_and_rollback(self):
        self.assertTrue(apply_hud_patches(self.repo, self.patches, False))
        self.assertFalse(apply_hud_patches(self.repo, self.patches, False))
        self.assertIn('language = "zh-TW"', self.renderer.read_text())
        self.assertIn('gear_screen = True', self.renderer.read_text())
        self.assertTrue(apply_hud_patches(self.repo, self.patches, True))
        self.assertFalse(apply_hud_patches(self.repo, self.patches, True))
        self.assertEqual(self.renderer.read_text(), self.base)

    def test_upgrades_the_previous_locale_update(self):
        apply_hud_patches(self.repo, (self.locale,), False)
        self.assertTrue(apply_hud_patches(self.repo, self.patches, False))
        self.assertIn('language = "zh-TW"', self.renderer.read_text())
        self.assertIn('gear_screen = True', self.renderer.read_text())

    def test_adds_cluster_limit_to_an_installed_layout(self):
        layout = self.gear.with_name('carrot-hud-alert-positions.patch')
        layout.write_text(self.gear.read_text())
        receiver = self.repo / 'receiver.py'
        receiver.write_text('limit = 0\n')
        limit = self.gear.with_name(CLUSTER_LIMIT_PATCH)
        limit.write_text(''.join(unified_diff(
            ['limit = 0\n'], ['limit = 60\n'], 'a/receiver.py', 'b/receiver.py',
        )))
        base = (self.locale, layout)
        self.assertTrue(apply_hud_patches(self.repo, base, False))
        self.assertTrue(apply_hud_patches(self.repo, (*base, limit), False))
        self.assertFalse(apply_hud_patches(self.repo, (*base, limit), False))
        self.assertEqual(receiver.read_text(), 'limit = 60\n')
        self.assertTrue(apply_hud_patches(self.repo, (*base, limit), True))
        self.assertEqual(receiver.read_text(), 'limit = 0\n')
        self.assertEqual(self.renderer.read_text(), self.base)

    def test_conflict_leaves_other_patch_unapplied(self):
        local = self.base.replace('gear_screen = False', 'gear_screen = "custom"')
        self.renderer.write_text(local)
        with self.assertRaises(subprocess.CalledProcessError):
            apply_hud_patches(self.repo, self.patches, False)
        self.assertEqual(self.renderer.read_text(), local)

    def test_dependent_display_patches_roll_back_twice(self):
        alerts = self.gear.with_name('carrot-hud-nav-alerts.patch')
        alerts.write_text(self.gear.read_text())
        placement = alerts.with_name('carrot-hud-alert-placement.patch')
        intermediate = self.base.replace('gear_screen = False', 'gear_screen = True')
        final = intermediate.replace('gear_screen = True', 'gear_screen = "new"')
        placement.write_text(''.join(unified_diff(
            intermediate.splitlines(keepends=True), final.splitlines(keepends=True),
            'a/renderer.py', 'b/renderer.py', n=1,
        )))
        patches = (self.locale, alerts, placement)

        self.assertFalse(apply_hud_patches(self.repo, patches, True))
        self.assertTrue(apply_hud_patches(self.repo, patches[:-1], False))
        self.assertTrue(apply_hud_patches(self.repo, patches, False))
        self.assertFalse(apply_hud_patches(self.repo, patches, False))
        self.assertIn('gear_screen = "new"', self.renderer.read_text())
        self.assertTrue(apply_hud_patches(self.repo, patches, True))
        self.assertFalse(apply_hud_patches(self.repo, patches, True))
        self.assertEqual(self.renderer.read_text(), self.base)


class GearRenderUpgradeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.repo = root / 'renderer'
        subprocess.run(['git', 'init', '-q', self.repo], check=True)
        self.renderer = self.repo / RENDERER
        self.renderer.parent.mkdir(parents=True)
        docstring = '        """Draw one frame."""\n'
        original = (
            'class ClusterUiRenderer:\n'
            '    def render(self, state, signal_lights=None):\n'
            + docstring
            + '        if signal_lights is None:\n'
            '            signal_lights = self._turn_signal_lights(state)\n'
            '        self._draw_hud(state, signal_lights)\n'
        )
        hook = (
            '        gear = gear_screen(state)\n'
            '        if gear is not None:\n'
            '            self._gear_screens.draw(self, state, gear)\n'
            '            return\n\n'
        )
        self.gear = root / GEAR_PATCH
        diff = unified_diff(original.splitlines(keepends=True),
                            original.replace(docstring, docstring + hook).splitlines(keepends=True),
                            f'a/{RENDERER}', f'b/{RENDERER}')
        self.gear.write_text(f'diff --git a/{RENDERER} b/{RENDERER}\n' + ''.join(diff))
        self.local = original.replace(docstring, '        """Draw one frame with the local map overlay."""\n'
                                                '        self._refresh_local_map(state)\n')
        self.renderer.write_text(self.local)

    def test_update_and_rollback_keep_local_render_code(self):
        old_check = subprocess.run(['git', '-C', self.repo, 'apply', '--check', self.gear], capture_output=True)
        self.assertNotEqual(old_check.returncode, 0)
        self.assertTrue(apply_hud_patches(self.repo, (self.gear,), False))
        self.assertFalse(apply_hud_patches(self.repo, (self.gear,), False))
        installed = self.renderer.read_text()
        self.assertEqual(installed.count('self._gear_screens.draw(self, state, gear)'), 1)
        self.assertIn('self._refresh_local_map(state)', installed)
        self.assertIn('"""Draw one frame with the local map overlay."""', installed)
        self.assertTrue(apply_hud_patches(self.repo, (self.gear,), True))
        self.assertFalse(apply_hud_patches(self.repo, (self.gear,), True))
        self.assertEqual(self.renderer.read_text(), self.local)

    def test_later_failure_reverses_the_adapted_patch(self):
        invalid_patch = self.gear.with_name('invalid.patch')
        invalid_patch.write_text('invalid patch\n')
        with self.assertRaises(subprocess.CalledProcessError):
            apply_hud_patches(self.repo, (self.gear, invalid_patch), False)
        self.assertEqual(self.renderer.read_text(), self.local)

    def test_existing_custom_gear_logic_is_preserved(self):
        custom = self.local.replace('        self._refresh_local_map(state)\n',
                                    '        if gear_screen(state):\n'
                                    '            self._draw_my_gear_screen(state)\n')
        self.renderer.write_text(custom)
        with self.assertRaisesRegex(ValueError, 'P／R'):
            apply_hud_patches(self.repo, (self.gear,), False)
        self.assertEqual(self.renderer.read_text(), custom)
