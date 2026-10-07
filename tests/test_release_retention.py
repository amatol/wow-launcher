import json
from pathlib import Path
import tempfile
import unittest

from tools.prune_launcher_releases import build_plan, apply_plan


class ReleaseRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / 'public'
        self.releases = self.public / 'releases'
        self.releases.mkdir(parents=True)
        self.backups = self.root / 'backups'
        self.backups.mkdir()
        for version in ('20261002', '20261005', '20261006', '20261007'):
            for ext in ('exe', 'app.zip'):
                (self.releases / f'Dreamworld-{version}.{ext}').write_bytes(b'release')
        self.manifests('20261007')

    def manifests(self, version):
        entries = {}
        for platform, ext in (('windows', 'exe'), ('macos', 'app.zip')):
            entry = {'version': version, 'download_url': f'https://example.test/launcher/releases/Dreamworld-{version}.{ext}'}
            entries[platform] = entry
            name = 'launcher_manifest.json' if platform == 'windows' else 'launcher_manifest_macos.json'
            (self.public / name).write_text(json.dumps(entry))
        (self.public / 'manifest.json').write_text(json.dumps({'version': version, 'launchers': entries}))

    def backup(self, folder_date, version):
        path = self.backups / f'launchers-{folder_date}'
        path.mkdir()
        (path / 'launcher_manifest.json').write_text(json.dumps({'version': version}))
        return path

    def test_keeps_three_versions_and_only_their_backups(self):
        old = self.backup('20261005', '20261002')
        retained = self.backup('20261006', '20261005')
        addon = self.releases / 'DreamQuestMap-20261002.zip'
        addon.write_bytes(b'addon')
        client_manifest = self.releases / 'manifest-20261002.json'
        client_manifest.write_bytes(b'client')
        archived_launcher = self.releases / 'launcher_manifest-20261002.json'
        archived_launcher.write_bytes(b'launcher')
        plan = build_plan(self.public, self.backups)
        self.assertEqual(plan['retained_versions'], ['20261007', '20261006', '20261005'])
        apply_plan(plan)
        self.assertFalse(old.exists())
        self.assertTrue(retained.exists())
        self.assertTrue(addon.exists())
        self.assertTrue(client_manifest.exists())
        self.assertFalse(archived_launcher.exists())
        self.assertEqual(len(list(self.releases.glob('Dreamworld-*'))), 6)
        self.assertEqual(build_plan(self.public, self.backups)['bytes_to_remove'], 0)

    def test_refuses_to_delete_version_referenced_by_active_manifest(self):
        self.manifests('20261002')
        with self.assertRaises(ValueError):
            build_plan(self.public, self.backups)
        self.assertTrue((self.releases / 'Dreamworld-20261002.exe').exists())

    def test_manifest_change_prevents_all_deletions(self):
        plan = build_plan(self.public, self.backups)
        self.manifests('20261006')
        with self.assertRaises(RuntimeError):
            apply_plan(plan)
        self.assertTrue((self.releases / 'Dreamworld-20261002.exe').exists())

    def test_unknown_backup_blocks_cleanup(self):
        (self.backups / 'launchers-20261001').mkdir()
        with self.assertRaises(ValueError):
            build_plan(self.public, self.backups)
        self.assertTrue((self.releases / 'Dreamworld-20261002.exe').exists())

    def test_symlink_replacement_prevents_deletion(self):
        plan = build_plan(self.public, self.backups)
        path = self.releases / 'Dreamworld-20261002.exe'
        path.unlink()
        external = self.root / 'important'
        external.write_bytes(b'keep')
        try:
            path.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest('Создание symlink недоступно на этой платформе')
        with self.assertRaises(RuntimeError):
            apply_plan(plan)
        self.assertEqual(external.read_bytes(), b'keep')
        self.assertTrue((self.releases / 'Dreamworld-20261002.app.zip').exists())

    def test_legacy_version_suffix_is_one_release_date(self):
        (self.releases / 'Dreamworld-2026080101.exe').write_bytes(b'legacy')
        plan = build_plan(self.public, self.backups)
        apply_plan(plan)
        self.assertFalse((self.releases / 'Dreamworld-2026080101.exe').exists())


if __name__ == '__main__':
    unittest.main()
