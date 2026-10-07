import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).resolve().parents[1] / 'scripts/prepare_upstream.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ProtocolTests(unittest.TestCase):
    def test_matching_protocol_allowed(self):
        prepare.check_protocol('public static let protocolVersion: UInt16 = 2', 2)

    def test_protocol_three_blocked(self):
        with self.assertRaisesRegex(prepare.CompatibilityError, '官方 protocol 3'):
            prepare.check_protocol('public static let protocolVersion: UInt16 = 3', 2)

    def test_missing_constant_blocked(self):
        with self.assertRaises(prepare.CompatibilityError):
            prepare.check_protocol('changed format', 2)


if __name__ == '__main__':
    unittest.main()
