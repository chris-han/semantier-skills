import tempfile
import unittest
from pathlib import Path
from publish_official_skills import inventory, catalog_bytes, publish, LocalStore


class InventoryTests(unittest.TestCase):
    def test_read_only_inventory_and_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'SKILL.md').write_text('---\nname: semantier--demo\n---\nFixture', encoding='utf-8')
            before = (root/'SKILL.md').read_bytes()
            args = dict(slug='demo', version='1.0.0', license_id='MIT', source_commit='a'*40)
            first = inventory(root, **args)
            self.assertEqual(first, inventory(root, **args))
            self.assertEqual((root/'SKILL.md').read_bytes(), before)
            self.assertTrue(all(p.startswith('skills/v1/packages/') for p in first['objects']))
            with self.assertRaises(ValueError):
                inventory(root, **{**args, 'slug': '../releases'})
            (root/'CON.txt').write_text('unsafe', encoding='utf-8')
            with self.assertRaises(ValueError):
                inventory(root, **args)



class PublicationTests(unittest.TestCase):
    def setUp(self):
        import json
        self.json = json
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.release = self.root/'release'
        self.release.mkdir()
        (self.release/'SKILL.md').write_text('---\nname: semantier--demo\n---\nLocal release A', encoding='utf-8')
        self.info = inventory(self.release, slug='demo', version='1.0.0', license_id='MIT', source_commit='a'*40)
        self.catalog = {'schema': 1, 'registry_id': 'semantier', 'sequence': 1, 'issued_at': '2026-11-19T00:00:00Z', 'expires_at': '2099-01-01T00:00:00Z', 'publisher': {'id': 'semantier', 'name': 'Semantier', 'repository': 'https://example.org/source', 'contact': 'fixture@example.org'}, 'skills': [{'slug': 'demo', 'name': 'Demo', 'description': 'Local fixture', 'tags': [], 'category': 'test', 'license': 'MIT', 'homepage': 'https://example.org', 'source_repository': 'https://example.org/source', 'source_commit': 'a'*40, 'source_path': 'skills/demo', 'type': 'skill', 'latest_version': '1.0.0', 'versions': [{'version': '1.0.0', 'source_commit': 'a'*40, 'released_at': '2026-11-19T00:00:00Z', 'compatibility': {}, 'manifest': self.info['manifest']}]}]}
        self.store = LocalStore(self.root/'objects')

    def publish(self, expected=None):
        return publish(self.catalog, {('demo', '1.0.0'): self.release}, self.store, expected_catalog_digest=expected)

    def test_plain_catalog_and_controlled_replacement(self):
        raw = catalog_bytes(self.catalog)
        self.assertEqual(self.json.loads(raw), self.catalog)
        result = self.publish()
        self.assertEqual(self.store.get('skills/v1/catalog.json', 2*1024*1024), raw)
        self.assertEqual(result['release_count'], 1)
        with self.assertRaisesRegex(ValueError, 'catalog changed'):
            self.publish()
        self.catalog['sequence'] = 2
        self.publish(result['catalog_digest'])
        with self.assertRaisesRegex(ValueError, 'concurrent catalog'):
            self.store.replace('skills/v1/catalog.json', raw, result['catalog_digest'])

    def test_corrupt_readback_keeps_catalog_absent(self):
        get = self.store.get
        self.store.get = lambda key, limit: b'corrupt' if '/packages/' in key else get(key, limit)
        with self.assertRaisesRegex(ValueError, 'readback failed'):
            self.publish()
        self.assertIsNone(get('skills/v1/catalog.json', 1024))

    def test_failed_upload_keeps_catalog_absent(self):
        def outage(*args):
            raise OSError('provider outage')
        self.store.put_if_absent = outage
        with self.assertRaises(OSError):
            self.publish()
        self.assertIsNone(self.store.get('skills/v1/catalog.json', 1024))

    def test_immutable_releases_and_artifact_paths(self):
        first = self.publish()
        before = self.store.get('skills/v1/catalog.json', 2*1024*1024)
        self.catalog['sequence'] = 2
        self.catalog['skills'][0]['versions'][0]['source_commit'] = 'b'*40
        with self.assertRaisesRegex(ValueError, 'immutable releases'):
            self.publish(first['catalog_digest'])
        self.assertEqual(self.store.get('skills/v1/catalog.json', 2*1024*1024), before)
        with self.assertRaises(ValueError):
            self.store.put_if_absent(self.info['objects'][0], b'changed')
        with self.assertRaises(ValueError):
            self.store.put_if_absent('releases/forbidden', b'no')

    def test_bad_manifest_fails_before_any_upload(self):
        self.catalog['skills'][0]['versions'][0]['manifest']['../escape'] = {'size': 0, 'sha256': '0'*64}
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(list((self.root/'objects').iterdir()), [])

    def test_file_changes_fail_without_catalog_replacement(self):
        (self.release/'SKILL.md').write_bytes(b'changed after preparation')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertIsNone(self.store.get('skills/v1/catalog.json', 1024))


if __name__ == '__main__':
    unittest.main()
