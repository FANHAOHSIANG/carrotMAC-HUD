import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('commaview_check', ROOT / 'scripts/check_commaview.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class PreflightTests(unittest.TestCase):
  def test_explicit_device_address_only(self):
    self.assertEqual(check.version_url(' 192.168.1.42 '), 'http://192.168.1.42:5002/commaview/version')
    self.assertEqual(check.version_url('::1'), 'http://[::1]:5002/commaview/version')
    for host in ('https://host/path', 'user:password@host', '192.168.1.1/repair', '0.0.0.0', '224.0.0.1', ''):
      with self.assertRaises(ValueError):
        check.version_url(host)

  def response(self, body):
    class Opener:
      def open(inner, request, timeout):
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.full_url, 'http://127.0.0.1:5002/commaview/version')
        self.assertIsNone(request.data)
        self.assertEqual(dict(request.header_items()), {'Accept': 'application/json'})
        self.assertEqual(timeout, 3)
        return io.BytesIO(body)
    with patch.object(check.urllib.request, 'build_opener', return_value=Opener()):
      return check.check_version('127.0.0.1')

  def test_only_allowlisted_version_values_appear_in_report(self):
    value = {'runtimeVersion': '0.0.59-beta', 'token': 'secret', 'deviceName': 'private', 'version': 'secret'}
    result = self.response(json.dumps(value).encode())
    self.assertIn('0.0.59-beta', result)
    self.assertNotIn('secret', result)
    self.assertNotIn('private', result)

  def test_invalid_and_oversized_server_reply(self):
    self.assertIn('格式不符', self.response(b'[]'))
    self.assertIn('無法讀取', self.response(b'<html>login</html>'))
    self.assertIn('大小限制', self.response(b'x' * 32769))

  def test_auth_required_does_not_attempt_pairing(self):
    with patch.object(check.urllib.request, 'build_opener') as factory:
      factory.return_value.open.side_effect = urllib.error.HTTPError('http://device', 401, 'secret', {}, None)
      result = check.check_version('127.0.0.1')
      self.assertIn('HTTP 401', result)
      self.assertNotIn('secret', result)
      self.assertEqual(factory.return_value.open.call_count, 1)

  def test_redirect_cannot_move_probe_to_another_endpoint(self):
    self.assertIsNone(check.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://other/repair'))

  def test_missing_local_install_is_reported_without_creating_files(self):
    with tempfile.TemporaryDirectory() as temp:
      base = Path(temp)
      lines = check.local_status(base, base / 'cache', duration=0)
      self.assertIn('未確認', lines[0])
      self.assertIn('未收到', lines[1])
      self.assertIn('未確認', lines[2])
      self.assertEqual(list(base.iterdir()), [])


if __name__ == '__main__':
  unittest.main()
