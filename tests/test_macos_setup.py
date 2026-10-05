import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from core.macos_setup import prepare_game_config, native_runtime_ready, runtime_files, prepare_wine_prefix


class MacSetupTests(unittest.TestCase):
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
            with patch('core.macos_setup.subprocess.run') as run, patch('core.macos_setup.urllib.request.urlopen') as download:
                prepare_wine_prefix(Path(directory), directory, {'WINEPREFIX': str(prefix)}, None)
                run.assert_not_called()
                download.assert_not_called()
