import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


receiver = module('nav_receiver', 'overlays/nav-preview/hud_map_receiver.py')
installer = module('nav_installer', 'scripts/install_nav_preview.py')


class PreviewTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        output = io.BytesIO()
        Image.new('L', (256, 256), 120).save(output, format='PNG')
        self.data = output.getvalue()
        self.clock = 100.
        self.record = {'params': {'ClusterHudScreenMode': 'Nw=='}, 'nav_map_preview': {
            'age': .1, 'sha256': hashlib.sha256(self.data).hexdigest(),
            'png': base64.b64encode(self.data).decode()}}
        self.snapshot = (99.9, self.record)
        self.subject = receiver.NavPreview(lambda: self.snapshot, self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def read(self):
        with patch.object(receiver.time, 'monotonic', return_value=self.clock):
            return self.subject.preview()

    def test_mac_cache_and_exact_png_without_app_rebuild(self):
        target, fresh = self.read()
        self.assertTrue(fresh)
        self.assertEqual(target, self.directory / 'nav-map.png')
        self.assertEqual(target.read_bytes(), self.data)
        mtime = target.stat().st_mtime_ns
        self.assertTrue(self.read()[1])
        self.assertEqual(target.stat().st_mtime_ns, mtime)

    def test_stale_snapshot_and_disconnect_hide_cached_map(self):
        self.assertTrue(self.read()[1])
        self.clock += .5
        self.assertFalse(self.read()[1])
        self.clock = 100.
        self.snapshot = None
        self.assertFalse(self.read()[1])

    def test_mode_source_expiry_and_bad_ages(self):
        self.record['params']['ClusterHudScreenMode'] = 'MA=='
        self.assertFalse(self.read()[1])
        self.record['params']['ClusterHudScreenMode'] = 'Nw=='
        for age in [-1, 1.95, 2, float('nan'), float('inf')]:
            with self.subTest(age=age):
                self.record['nav_map_preview']['age'] = age
                self.assertFalse(self.read()[1])

    def test_invalid_hash_size_base64_and_truncated_png(self):
        value = self.record['nav_map_preview']
        value['sha256'] = '0' * 64
        self.assertFalse(self.read()[1])
        for data in [b'bad', self.data[:30], b'x' * (receiver.MAX_BYTES + 1)]:
            value.update(png=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
            self.assertFalse(self.read()[1])
        value['png'] = '!!!!'
        self.assertFalse(self.read()[1])
        self.assertFalse(self.subject.path.exists())

    def test_new_image_replaces_texture_file(self):
        self.assertTrue(self.read()[1])
        from PIL import Image
        output = io.BytesIO()
        Image.new('L', (256, 256), 50).save(output, format='PNG')
        data = output.getvalue()
        self.record['nav_map_preview'].update(png=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
        self.assertTrue(self.read()[1])
        self.assertEqual(self.subject.path.read_bytes(), data)


class InstallerTests(unittest.TestCase):
    def test_existing_official_renderer_only_changes_preview_source(self):
        source = '''class Renderer:
    def _draw_nav_model_map(self):
        from openpilot.selfdrive.navigation.preview import PREVIEW_PATH, preview_fresh
        self._nav_model_fresh = preview_fresh()
        return PREVIEW_PATH
    def control(self):
        return "unchanged"
'''
        result = installer.receiver_renderer(source)
        self.assertIn('from hud_map_receiver import preview', result)
        self.assertIn('PREVIEW_PATH, self._nav_model_fresh = preview()', result)
        self.assertIn('    def control(self):\n        return "unchanged"', result)
        self.assertEqual(installer.receiver_renderer(result), result)

    def test_unknown_renderer_is_rejected(self):
        with self.assertRaises(ValueError):
            installer.receiver_renderer('def _draw_nav_model_map():\n    pass\n')

    def test_install_restore_and_failed_copy_preserve_existing_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper, staged = root / 'helper', root / 'stage'
            for name in installer.FILES:
                target = staged / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('new')
            for name in installer.FILES[:2]:
                target = helper / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('old')
            backup = root / 'backup'
            installer.install(helper, staged, backup)
            self.assertTrue(all((helper / name).read_text() == 'new' for name in installer.FILES))
            installer.restore(helper, backup)
            self.assertFalse((helper / installer.RECEIVER).exists())
            self.assertTrue(all((helper / name).read_text() == 'old' for name in installer.FILES[:2]))
            real_replace = installer.replace
            def fail(source, target):
                if source == staged / installer.CONFIG:
                    raise OSError('simulated failed install')
                return real_replace(source, target)
            with patch.object(installer, 'replace', side_effect=fail):
                with self.assertRaises(OSError):
                    installer.install(helper, staged, root / 'failed-backup')
            self.assertFalse((helper / installer.RECEIVER).exists())
            self.assertTrue(all((helper / name).read_text() == 'old' for name in installer.FILES[:2]))


if __name__ == '__main__':
    unittest.main()
