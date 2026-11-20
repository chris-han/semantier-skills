import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from official_skill_oss import OssStore, OssError


class OssStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home/'.aliyun').mkdir()
        self.home_patch = patch('official_skill_oss.Path.home', return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.credentials = {'AccessKeyId': 'test-id', 'AccessKeySecret': 'test-secret', 'SecurityToken': 'test-token'}
        self.store = OssStore(self.credentials, qualification_run='test-run')

    def test_missing_is_distinct_from_denial_and_oversize(self):
        with patch('official_skill_oss.subprocess.run', return_value=subprocess.CompletedProcess([], 2, b'', b'Error Code: NoSuchKey.')):
            self.assertIsNone(self.store.get(self.store.catalog_key, 10))
        with patch('official_skill_oss.subprocess.run', return_value=subprocess.CompletedProcess([], 2, b'', b'Error Code: AccessDenied.')):
            with self.assertRaises(OssError):
                self.store.get(self.store.catalog_key, 10)
        with patch('official_skill_oss.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'x'*11, b'')) as call:
            with self.assertRaisesRegex(ValueError, 'bound'):
                self.store.get(self.store.catalog_key, 10)
            args = call.call_args.args[0]
            self.assertIn('--head', args)
            self.assertEqual(args[args.index('--head')+1], '11')
            self.assertEqual(args[args.index('--config-file')+1], '/dev/null')
            self.assertNotIn('test-secret', args)
            self.assertEqual(call.call_args.kwargs['env']['OSS_SESSION_TOKEN'], 'test-token')

    def test_no_missing_credentials_or_unsafe_keys(self):
        with self.assertRaises(ValueError):
            OssStore({})
        for key in ['releases/no', 'skills/v1/../outside', 'skills/v1/catalog.json', 'skills/v1/packages/a/../../x']:
            with self.assertRaises(ValueError):
                self.store.get(key, 10)
        with self.assertRaises(ValueError):
            self.store.replace('skills/v1/catalog.json', b'{}', None)
        # Preserve ordinary source-file names accepted by the existing manifest.
        self.assertEqual(self.store._key(self.store.package_prefix+'参考.md'), self.store.package_prefix+'参考.md')

    def test_collisions_only_reuse_identical_bytes(self):
        key = self.store.package_prefix+'probe.txt'
        self.store._put = lambda *a, **kw: (_ for _ in ()).throw(OssError('FileAlreadyExists'))
        self.store.get = lambda *a: b'same'
        self.store.put_if_absent(key, b'same')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.store.put_if_absent(key, b'changed')

    def test_stale_replacement_and_failed_readback(self):
        remote = {self.store.catalog_key: b'old'}
        self.store.get = lambda key, limit: remote.get(key)
        def put(key, raw, **kw):
            remote[key] = raw
        self.store._put = put
        old = hashlib.sha256(b'old').hexdigest()
        self.store.replace(self.store.catalog_key, b'new', old)
        with self.assertRaisesRegex(ValueError, 'concurrent'):
            self.store.replace(self.store.catalog_key, b'stale', old)
        self.assertEqual(remote[self.store.catalog_key], b'new')
        self.store._put = lambda *a, **kw: None
        with self.assertRaisesRegex(OssError, 'readback'):
            self.store.replace(self.store.catalog_key, b'unwritten', hashlib.sha256(b'new').hexdigest())
        self.assertTrue(self.store.lock_path.read_bytes())
        with self.assertRaisesRegex(OssError, 'operator recovery'):
            self.store.replace(self.store.catalog_key, b'blocked', hashlib.sha256(b'new').hexdigest())

    def test_lock_shared_between_namespaces_and_symlink_refused(self):
        other = OssStore(self.credentials, qualification_run='other-run')
        self.assertEqual(self.store.lock_path, other.lock_path)
        target = self.home/'target'
        target.write_bytes(b'keep')
        self.store.lock_path.symlink_to(target)
        self.store.get = lambda *a: None
        with self.assertRaises(OSError):
            self.store.replace(self.store.catalog_key, b'{}', None)
        self.assertEqual(target.read_bytes(), b'keep')

    def test_assume_role_checks_identity_and_does_not_expose_errors(self):
        payload = {'AssumedRoleUser': {'Arn': 'acs:ram::1775489628552482:role/wrong/session'}, 'Credentials': self.credentials}
        with patch('official_skill_oss.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b'')):
            with self.assertRaisesRegex(ValueError, 'identity'):
                OssStore.from_operator(qualification_run='test-run')
        with patch('official_skill_oss.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'test-secret', b'test-token')):
            with self.assertRaises(OssError) as error:
                OssStore.from_operator()
            self.assertNotIn('test-secret', str(error.exception))
            self.assertNotIn('test-token', str(error.exception))


if __name__ == '__main__':
    unittest.main()
