import tempfile
import unittest
from pathlib import Path
from publish_official_skills import inventory


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


if __name__ == '__main__':
    unittest.main()
