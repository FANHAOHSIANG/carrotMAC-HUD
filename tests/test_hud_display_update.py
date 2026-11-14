from difflib import unified_diff
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_hud_locale import apply_hud_patches


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

    def test_conflict_leaves_other_patch_unapplied(self):
        local = self.base.replace('gear_screen = False', 'gear_screen = "custom"')
        self.renderer.write_text(local)
        with self.assertRaises(subprocess.CalledProcessError):
            apply_hud_patches(self.repo, self.patches, False)
        self.assertEqual(self.renderer.read_text(), local)
