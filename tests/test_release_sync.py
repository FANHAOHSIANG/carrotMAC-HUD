"""Check release selection and prevent automatic changes to the C4 pairing."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


resolver = module('resolve_upstream')
sync = module('sync_versions')
OLD = 'a' * 40
NEW = 'b' * 40


class ReleaseSyncTests(unittest.TestCase):
    def current(self):
        return {'schema': 2, 'jetlink_revision': OLD, 'jetlink_version': '0.8.3',
                'carrot_revision': 'c' * 40, 'comma_revision': 'd' * 40, 'protocol': 3}

    def test_scheduled_new_release_is_immutable_and_promotable(self):
        result = resolver.resolve(self.current(), 'schedule', release_loader=lambda: {'tag_name': 'v0.8.5'},
                                  tag_loader=lambda tag: NEW)
        self.assertEqual(result, {'ref': NEW, 'release': 'v0.8.5', 'prepare': True, 'promote': True})

    def test_unchanged_release_skips_expensive_build(self):
        result = resolver.resolve(self.current(), 'schedule', release_loader=lambda: {'tag_name': 'v0.8.3'},
                                  tag_loader=lambda tag: OLD)
        self.assertFalse(result['prepare'])

    def test_pr_and_push_only_validate_the_pin(self):
        for event in ('push', 'pull_request'):
            result = resolver.resolve(self.current(), event, 'latest', release_loader=lambda: self.fail('network'))
            self.assertEqual(result, {'ref': OLD, 'prepare': True, 'promote': False})

    def test_manual_main_or_tag_never_auto_promotes(self):
        for ref in ('main', 'v0.8.5'):
            result = resolver.resolve(self.current(), 'workflow_dispatch', ref)
            self.assertEqual(result, {'ref': ref, 'prepare': True, 'promote': False})

    def test_unstable_or_missing_release_is_rejected(self):
        for release in ({}, {'tag_name': 'edge'}, {'tag_name': 'v0.9.0-rc1'},
                        {'tag_name': 'v0.8.5', 'prerelease': True}, {'tag_name': 'v0.8.5', 'draft': True}):
            with self.assertRaises(ValueError):
                resolver.stable_tag(release)

    def test_annotated_tag_uses_peeled_commit(self):
        output = f'{OLD}\trefs/tags/v0.8.5\n{NEW}\trefs/tags/v0.8.5^{{}}\n'
        self.assertEqual(resolver.peeled_tag(output, 'v0.8.5'), NEW)
        self.assertEqual(resolver.peeled_tag(f'{NEW}\trefs/tags/v0.8.5\n', 'v0.8.5'), NEW)
        with self.assertRaises(ValueError):
            resolver.peeled_tag('', 'v0.8.5')

    def test_revision_and_product_version_can_change(self):
        current = self.current()
        candidate = dict(current, jetlink_revision=NEW, jetlink_version='0.8.5')
        sync.validate(current, candidate)

    def test_protocol_schema_renderer_or_c4_changes_are_rejected(self):
        current = self.current()
        for key, value in [('protocol', 4), ('schema', 3), ('carrot_revision', NEW), ('comma_revision', NEW)]:
            with self.assertRaises(ValueError):
                sync.validate(current, dict(current, **{key: value}))

    def test_bad_revision_and_product_version_are_rejected(self):
        for key, value in [('jetlink_revision', 'main'), ('jetlink_version', '0.8.5-rc1')]:
            with self.assertRaises(ValueError):
                sync.validate(self.current(), dict(self.current(), **{key: value}))


if __name__ == '__main__':
    unittest.main()
