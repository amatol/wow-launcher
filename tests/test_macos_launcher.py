import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
import zipfile

from config import app_bundle_path, game_directory
from core.launcher_bundle import extract_app, install_app, sync_companion, companion_needed
from core.macos import launch_wow_macos
from tools.generate_manifest import build_manifest


class MacLauncherTests(unittest.TestCase):
    def archive(self, path, extra=None):
        with zipfile.ZipFile(path, 'w') as archive:
            item = zipfile.ZipInfo('Dreamworld.app/Contents/MacOS/Dreamworld')
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(item, b'launcher')
            if extra:
                archive.writestr(extra, b'bad')

    def test_bundle_uses_client_directory_instead_of_contents_macos(self):
        with patch('config.sys.platform', 'darwin'), patch('config.sys.frozen', True, create=True), patch('config.sys.executable', '/client/Dreamworld.app/Contents/MacOS/Dreamworld'):
            self.assertEqual(game_directory(), '/client')
            self.assertEqual(app_bundle_path(), '/client/Dreamworld.app')

    def test_wine_prefix_stays_in_client_and_command_preserves_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / 'Dreamworld.app'
            for name in ('Wine/bin/wine', 'Patching/rosettax87/rosettax87'):
                path = bundle / 'Contents/Resources' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            game = root / 'Client with spaces'
            game.mkdir()
            wow = game / 'Wow.exe'
            wow.touch()
            process = Mock()
            process.wait.side_effect = subprocess.TimeoutExpired('wine', 2)
            with patch('core.macos.app_bundle_path', return_value=str(bundle)), patch('core.macos.subprocess.Popen', return_value=process) as launch, patch.dict(os.environ, {'WINEPREFIX': '/wrong', 'WINEARCH': 'win32'}):
                launch_wow_macos(wow, str(game))
            args, kwargs = launch.call_args
            self.assertEqual(args[0][1], str(wow))
            self.assertEqual(kwargs['env']['WINEPREFIX'], str(game / '.dreamworld-wine'))
            self.assertNotIn('WINEARCH', kwargs['env'])
            self.assertEqual(kwargs['cwd'], str(game))

    def test_install_preserves_executable_and_prefix_and_windows_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'app.zip'
            self.archive(archive)
            (root / 'Dreamworld.exe').write_bytes(b'windows')
            (root / '.dreamworld-wine').mkdir()
            (root / '.dreamworld-wine/user.reg').write_text('settings')
            install_app(archive, root)
            install_app(archive, root)
            self.assertTrue(os.access(root / 'Dreamworld.app/Contents/MacOS/Dreamworld', os.X_OK))
            self.assertEqual((root / '.dreamworld-wine/user.reg').read_text(), 'settings')
            self.assertEqual((root / 'Dreamworld.exe').read_bytes(), b'windows')

    def test_rejects_traversal_without_replacing_existing_app(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'Dreamworld.app'
            old.mkdir()
            (old / 'original').touch()
            archive = root / 'app.zip'
            self.archive(archive, 'Dreamworld.app/../../escape')
            with self.assertRaises(ValueError):
                install_app(archive, root)
            self.assertTrue((old / 'original').exists())
            self.assertFalse((root.parent / 'escape').exists())

    def test_manifest_excludes_wine_and_app(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('Wow.exe', 'Dreamworld.app/Contents/MacOS/Dreamworld', '.dreamworld-wine/user.reg'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual([f['path'] for f in build_manifest(root, '20261002', 'https://example.test')['files']], ['Wow.exe'])


class CompanionTests(unittest.TestCase):
    def test_windows_downloads_mac_bundle_and_reuses_matching_installation(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'source.zip'
            MacLauncherTests().archive(archive)
            payload = archive.read_bytes()
            raw = {'launchers': {'macos': {'download_url': 'https://example.test/mac.zip',
                   'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}}}
            def download(url, destination, *args, **kwargs):
                Path(destination).write_bytes(payload)
                return True, ''
            with patch('core.launcher_bundle.sys.platform', 'win32'), patch('core.launcher_bundle.download_with_retries', side_effect=download) as fetch:
                self.assertTrue(companion_needed(raw, directory))
                sync_companion(raw, directory)
                self.assertFalse(companion_needed(raw, directory))
                sync_companion(raw, directory)
                fetch.assert_called_once()

    def test_failed_companion_download_keeps_existing_windows_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'Dreamworld.exe'
            exe.write_bytes(b'old')
            raw = {'launchers': {'windows': {'download_url': 'https://example.test/win.exe',
                   'size': 3, 'sha256': '0' * 64}}}
            with patch('core.launcher_bundle.sys.platform', 'darwin'), patch('core.launcher_bundle.download_with_retries', return_value=(False, 'error')):
                with self.assertRaises(RuntimeError):
                    sync_companion(raw, directory)
            self.assertEqual(exe.read_bytes(), b'old')
