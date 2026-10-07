import io
import os
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from core.macos_fonts import FONT_FILES, FONT_MARKER, corefonts_ready, prepare_corefonts


class CorefontsTests(unittest.TestCase):
    def install_files(self, prefix):
        fonts = prefix / 'drive_c/windows/Fonts'
        fonts.mkdir(parents=True, exist_ok=True)
        for name in FONT_FILES:
            (fonts / name).write_bytes(b'\x00\x01\x00\x00' + b'\0' * 2048)

    def test_marker_does_not_hide_missing_or_corrupt_font(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            (prefix / FONT_MARKER).touch()
            self.assertFalse(corefonts_ready(prefix))
            self.install_files(prefix)
            self.assertTrue(corefonts_ready(prefix))
            (prefix / 'drive_c/windows/Fonts/arial.ttf').write_bytes(b'corrupt' * 300)
            self.assertFalse(corefonts_ready(prefix))

    def test_existing_ready_prefix_does_not_download_or_run_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            self.install_files(prefix)
            (prefix / FONT_MARKER).touch()
            with patch('core.macos_fonts.subprocess.Popen') as launch:
                prepare_corefonts(prefix, directory, {'WINEPREFIX': directory}, io.BytesIO())
            launch.assert_not_called()

    def test_failed_install_is_retryable_and_preserves_existing_prefix(self):
        with tempfile.TemporaryDirectory(prefix='fonts with spaces ') as directory:
            root = Path(directory)
            tools = root / 'resources/Wine/font-tools'
            tools.mkdir(parents=True)
            for name in ('winetricks', 'cabextract'):
                (tools / name).touch()
            prefix = root / '.dreamworld-wine'
            prefix.mkdir()
            (prefix / 'user.reg').write_text('settings')
            env = {'WINEPREFIX': str(prefix), 'PATH': '/usr/bin:/bin'}
            process = Mock()
            process.wait.return_value = 1
            with patch('core.macos_fonts.subprocess.Popen', return_value=process) as launch:
                with self.assertRaisesRegex(RuntimeError, 'Не удалось установить'):
                    prepare_corefonts(root / 'resources', directory, env, io.BytesIO())
                self.assertFalse((prefix / FONT_MARKER).exists())
                def success(**kwargs):
                    self.install_files(prefix)
                    return 0
                process.wait.side_effect = success
                prepare_corefonts(root / 'resources', directory, env, io.BytesIO())
            self.assertTrue((prefix / FONT_MARKER).is_file())
            self.assertEqual((prefix / 'user.reg').read_text(), 'settings')
            args, kwargs = launch.call_args
            self.assertEqual(args[0][-1], 'corefonts')
            self.assertEqual(kwargs['env']['WINE'], str(root / 'resources/Wine/bin/wine'))
            self.assertEqual(kwargs['env']['W_CACHE'], str(prefix / '.dreamworld-font-cache'))
            self.assertIn('--optout', args[0])
            self.assertEqual(env, {'WINEPREFIX': str(prefix), 'PATH': '/usr/bin:/bin'})

    @unittest.skipUnless(os.name == 'posix', 'Группы процессов Wine проверяются на POSIX')
    def test_timeout_stops_subprocess_group_and_never_marks_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'Wine/font-tools'
            tools.mkdir(parents=True)
            for name in ('winetricks', 'cabextract'):
                (tools / name).touch()
            process = Mock(pid=123)
            process.wait.side_effect = [subprocess.TimeoutExpired('winetricks', 600), 0]
            with patch('core.macos_fonts.subprocess.Popen', return_value=process), patch('core.macos_fonts.os.killpg') as kill:
                with self.assertRaisesRegex(RuntimeError, 'время ожидания'):
                    prepare_corefonts(root, directory, {'WINEPREFIX': directory}, io.BytesIO())
            kill.assert_called_once()
            self.assertFalse((root / FONT_MARKER).exists())
