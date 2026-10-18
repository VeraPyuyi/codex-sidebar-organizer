"""Build provenance and isolated upgrade/rollback; never starts a host client."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from test_sidebar_plan import ROOT

spec = importlib.util.spec_from_file_location('release_builder', ROOT/'scripts/build_release.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)


class ReleaseSafetyTests(unittest.TestCase):
    def test_manifest_covers_bytes_and_identifies_source(self):
        self.assertTrue(hasattr(b, 'provenance'), 'missing build provenance')
        entries = {'skill/a.txt': b'first', 'skill/b.txt': b'second'}
        report = b.provenance(entries)
        self.assertEqual(len(report['buildSha']), 40)
        self.assertTrue(report['pythonVersion'])
        self.assertEqual(report['files'], {k: hashlib.sha256(v).hexdigest() for k,v in entries.items()})
        self.assertTrue(b.verify_manifest(entries, report))
        entries['skill/a.txt'] = b'tampered'
        self.assertFalse(b.verify_manifest(entries, report))

    def test_duplicate_install_upgrade_and_rollback_in_temp_only(self):
        self.assertTrue(hasattr(b, 'installation_inventory'), 'missing duplicate diagnosis')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = root/'plugins/sidebar-organizer/skills/organize-sidebar'
            standalone = root/'skills/organize-sidebar'
            plugin.mkdir(parents=True); standalone.mkdir(parents=True)
            (plugin/'SKILL.md').write_text('old', encoding='utf-8')
            (standalone/'SKILL.md').write_text('new', encoding='utf-8')
            self.assertEqual(b.installation_inventory(root)['status'], 'duplicate')
            (standalone/'SKILL.md').unlink()
            self.assertEqual(b.installation_inventory(root)['status'], 'single')
            saved = (plugin/'SKILL.md').read_bytes()
            (plugin/'SKILL.md').write_bytes(b'upgraded')
            self.assertEqual(b.installation_inventory(root)['copies'][0]['sha256'], hashlib.sha256(b'upgraded').hexdigest())
            (plugin/'SKILL.md').write_bytes(saved)
            self.assertEqual(b.installation_inventory(root)['copies'][0]['sha256'], hashlib.sha256(b'old').hexdigest())

if __name__ == '__main__': unittest.main()
