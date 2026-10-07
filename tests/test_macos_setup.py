import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
import io
import hashlib
from core.macos_setup import prepare_game_config, native_runtime_ready, runtime_files, prepare_wine_prefix


class MacSetupTests(unittest.TestCase):
    def setUp(self):
        migration = patch('core.macos_setup.ensure_runtime_prefix')
        migration.start()
        self.addCleanup(migration.stop)
        fonts = patch('core.macos_setup.prepare_corefonts')
        fonts.start()
        self.addCleanup(fonts.stop)

    def test_preserves_non_utf8_crlf_and_existing_values_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'WTF/Config.wtf'
            config.parent.mkdir()
            original = b'// \xcf\xf0\xe8\xe2\xe5\xf2\r\nSET locale "ruRU"\r\nset GXRESOLUTION "1920x1080"'
            config.write_bytes(original)
            prepare_game_config(directory)
            updated = config.read_bytes()
            self.assertTrue(updated.startswith(original + b'\r\n'))
            self.assertEqual(updated.count(b'1920x1080'), 1)
            self.assertNotIn(b'1280x800', updated)
            self.assertIn(b'SET gxWindow "1"\r\n', updated)
            self.assertEqual(config.with_name('Config.wtf.before-dreamworld-macos').read_bytes(), original)
            prepare_game_config(directory)
            self.assertEqual(config.read_bytes(), updated)

    def test_fresh_config_and_utf16_and_existing_fullscreen(self):
        for encoding in ('utf-16-le', 'utf-16-be'):
            with tempfile.TemporaryDirectory() as directory:
                prepare_game_config(directory)
                config = Path(directory) / 'WTF/Config.wtf'
                self.assertIn(b'SET gxResolution "1280x800"', config.read_bytes())
                bom = b'\xff\xfe' if encoding.endswith('le') else b'\xfe\xff'
                original = bom + 'SET gxWindow "0"\n// Привет\n'.encode(encoding)
                config.write_bytes(original)
                prepare_game_config(directory)
                self.assertTrue(config.read_bytes().startswith(original))
                self.assertIn('SET gxWindow "0"', config.read_bytes()[2:].decode(encoding))
                self.assertIn('SET gxResolution "1280x800"', config.read_bytes()[2:].decode(encoding))

    def test_utf8_bom_keeps_first_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'WTF/Config.wtf'
            config.parent.mkdir()
            original = b'\xef\xbb\xbfSET gxResolution "1920x1080"\n'
            config.write_bytes(original)
            prepare_game_config(directory)
            self.assertTrue(config.read_bytes().startswith(original))
            self.assertNotIn(b'1280x800', config.read_bytes())

    def test_builtin_dll_is_not_native_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in runtime_files(directory):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'MZ' + b'\0' * 62 + b'Wine builtin DLL')
            self.assertFalse(native_runtime_ready(directory))
            for path in runtime_files(directory):
                path.write_bytes(b'MZ' + b'\0' * 126)
            self.assertTrue(native_runtime_ready(directory))

    def test_ready_prefix_does_not_run_installers_or_download(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / '.dreamworld-wine'
            prefix.mkdir()
            (prefix / '.dreamworld-vcredist-v1').touch()
            (prefix / 'drive_c/windows/mono/mono-2.0').mkdir(parents=True)
            for path in runtime_files(prefix):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'MZ' + b'\0' * 126)
            with patch('core.macos_setup.subprocess.run') as run, patch('core.macos_setup.urllib.request.urlopen') as download, patch('core.macos_setup.prepare_corefonts') as fonts:
                prepare_wine_prefix(Path(directory), directory, {'WINEPREFIX': str(prefix)}, None)
                run.assert_not_called()
                download.assert_not_called()
                fonts.assert_called_once()


class PrefixFailureTests(unittest.TestCase):
    def setUp(self):
        migration = patch('core.macos_setup.ensure_runtime_prefix')
        migration.start()
        self.addCleanup(migration.stop)
        fonts = patch('core.macos_setup.prepare_corefonts')
        fonts.start()
        self.addCleanup(fonts.stop)

    def test_checksum_failure_never_runs_vc_installer_or_marks_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Path(directory) / 'resources'
            mono = resources / 'Wine/share/wine/mono/wine-mono-10.4.1-x86.msi'
            mono.parent.mkdir(parents=True)
            mono.touch()
            prefix = Path(directory) / '.dreamworld-wine'
            (prefix / 'drive_c/windows/mono/mono-2.0').mkdir(parents=True)
            with patch('core.macos_setup.run_wine_setup') as run, patch('core.macos_setup.urllib.request.urlopen', return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(RuntimeError, 'Контрольная сумма'):
                    prepare_wine_prefix(resources, directory, {'WINEPREFIX': str(prefix), 'ROSETTA_X87_PATH': '/game-only'}, Mock())
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[1], ['wineboot', '--init'])
            self.assertFalse((prefix / '.dreamworld-vcredist-v1').exists())

    def test_failed_installer_can_be_retried_and_only_success_marks_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            resources = Path(directory) / 'resources'
            mono = resources / 'Wine/share/wine/mono/wine-mono-10.4.1-x86.msi'
            mono.parent.mkdir(parents=True)
            mono.touch()
            prefix = Path(directory) / '.dreamworld-wine'
            (prefix / 'drive_c/windows/mono/mono-2.0').mkdir(parents=True)
            payload = b'test installer'
            digest = hashlib.sha256(payload).hexdigest()
            def install(wine, args, env, game_dir, log):
                if args[0].endswith('vc_redist.x64.exe'):
                    for path in runtime_files(prefix):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b'MZ' + b'\0' * 126)
            with patch('core.macos_setup.VC_HASHES', {'x86': digest, 'x64': digest}), patch('core.macos_setup.urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(payload)):
                with patch('core.macos_setup.run_wine_setup', side_effect=[None, RuntimeError('install failed')]):
                    with self.assertRaisesRegex(RuntimeError, 'install failed'):
                        prepare_wine_prefix(resources, directory, {'WINEPREFIX': str(prefix), 'ROSETTA_X87_PATH': '/game-only'}, Mock())
                self.assertFalse((prefix / '.dreamworld-vcredist-v1').exists())
                with patch('core.macos_setup.run_wine_setup', side_effect=install) as run:
                    prepare_wine_prefix(resources, directory, {'WINEPREFIX': str(prefix), 'ROSETTA_X87_PATH': '/game-only'}, Mock())
                    self.assertEqual(run.call_count, 3)
                    for call in run.call_args_list:
                        self.assertNotIn('ROSETTA_X87_PATH', call.args[2])
                self.assertTrue((prefix / '.dreamworld-vcredist-v1').is_file())


class BuiltinBackupTests(unittest.TestCase):
    def test_only_wine_stubs_are_backed_up_and_failure_restores_missing_files(self):
        from core.macos_setup import backup_builtin_vc_files, restore_missing_builtins
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'drive_c/windows/syswow64'
            folder.mkdir(parents=True)
            stub = folder / 'msvcp140.dll'
            builtin = b'MZ' + b'\0' * 62 + b'Wine builtin DLL'
            stub.write_bytes(builtin)
            native = folder / 'vcruntime140.dll'
            native.write_bytes(b'MZ native user file')
            moved = backup_builtin_vc_files(directory)
            self.assertEqual(len(moved), 1)
            self.assertFalse(stub.exists())
            self.assertEqual(moved[0][1].read_bytes(), builtin)
            self.assertEqual(native.read_bytes(), b'MZ native user file')
            restore_missing_builtins(moved)
            self.assertEqual(stub.read_bytes(), builtin)
            moved = backup_builtin_vc_files(directory)
            stub.write_bytes(b'MZ installed Microsoft file')
            restore_missing_builtins(moved)
            self.assertEqual(stub.read_bytes(), b'MZ installed Microsoft file')
