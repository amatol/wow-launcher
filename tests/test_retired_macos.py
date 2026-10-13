from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from core.launcher_bundle import cleanup_retired_macos, companion_needed, sync_companion, UpdateCancelled
from tools.generate_manifest import build_manifest


class RetirementTests(unittest.TestCase):
    def test_cleanup_preserves_game_and_removes_all_owned_components_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('Dreamworld.app/Contents/MacOS/Dreamworld', 'Dreamworld.app.old/old',
                         '.dreamworld-wine/user.reg', '.dreamworld-app-ab12_cde/partial',
                         'WTF/Config.wtf', 'Interface/AddOns/custom.lua', 'Data/game.MPQ',
                         'Wow.exe', 'Dreamworld.exe', '.dreamworld-wine.log',
                         '.dreamworld-wine.lock', '.dreamworld-launchers.json', 'Dreamworld.app.zip'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'preserve')
            self.assertTrue(companion_needed({}, root))
            with patch('requests.get', side_effect=AssertionError('must not download')):
                sync_companion({'launchers': {'macos': {'download_url': 'https://old'}}}, root)
            self.assertFalse(companion_needed({}, root))
            self.assertEqual(cleanup_retired_macos(root), 0)
            for name in ('WTF/Config.wtf', 'Interface/AddOns/custom.lua', 'Data/game.MPQ', 'Wow.exe', 'Dreamworld.exe'):
                self.assertEqual((root / name).read_bytes(), b'preserve')

    def test_symlinks_never_delete_external_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / 'game'; game.mkdir()
            external = root / 'external'; external.mkdir(); (external / 'keep').touch()
            try:
                (game / 'Dreamworld.app').symlink_to(external, target_is_directory=True)
                (game / '.dreamworld-wine').mkdir()
                (game / '.dreamworld-wine/dosdevices').symlink_to(external, target_is_directory=True)
            except OSError:
                self.skipTest('symlink unavailable')
            cleanup_retired_macos(game)
            self.assertTrue((external / 'keep').exists())
            self.assertEqual(list(game.iterdir()), [])

    def test_cancel_and_io_failure_can_be_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'Dreamworld.app'; p.mkdir(); (p / 'file').touch()
            with self.assertRaises(UpdateCancelled):
                sync_companion({}, temp, cancel_check=lambda: True)
            with patch('core.launcher_bundle.shutil.rmtree', side_effect=PermissionError), self.assertRaises(PermissionError):
                cleanup_retired_macos(temp)
            self.assertTrue(companion_needed({}, temp))
            cleanup_retired_macos(temp)
            self.assertFalse(companion_needed({}, temp))

    def test_manifest_never_restores_mac_and_keeps_tombstones(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = build_manifest(Path(temp), '20261013', 'https://test', {
                'launchers': {'windows': {}, 'macos': {}},
                'removed_files': ['Dreamworld.app/old']})
            self.assertEqual(manifest['launchers'], {'windows': {}})
            self.assertIn('Dreamworld.app/old', manifest['removed_files'])

    @unittest.skipIf(os.name == 'nt', 'bash cleanup runs on Mac/POSIX')
    def test_shell_cleanup_validates_target_and_preserves_external_symlink_target(self):
        script = Path(__file__).resolve().parents[1] / 'tools/remove-macos.sh'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / 'game with spaces'; game.mkdir()
            external = root / 'external'; external.mkdir(); (external / 'keep').touch()
            (game / 'Dreamworld.app').symlink_to(external, target_is_directory=True)
            result = subprocess.run(['bash', str(script), str(game)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            (game / 'Wow.exe').touch(); (game / 'Data').mkdir()
            subprocess.run(['bash', str(script), str(game)], check=True, capture_output=True)
            self.assertTrue((external / 'keep').exists())
            self.assertFalse((game / 'Dreamworld.app').exists())
