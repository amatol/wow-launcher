import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

from core.macos_prefix import ensure_runtime_prefix, prefix_lock, RUNTIME_ID, RUNTIME_MARKER


class PrefixMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.game = Path(temporary.name).resolve()
        self.resources = self.game / 'Dreamworld.app/Contents/Resources'
        (self.resources / 'Wine').mkdir(parents=True)
        (self.resources / 'Wine/dreamworld-runtime-id').write_text(RUNTIME_ID)
        self.prefix = self.game / '.dreamworld-wine'
        self.prefix.mkdir()
        (self.prefix / 'old.reg').write_text('old wine')
        self.env = {'WINEPREFIX': str(self.prefix)}
        self.log = io.BytesIO()

    def migrate(self):
        ensure_runtime_prefix(self.resources, self.game, self.env, self.log)

    def test_migration_once_preserves_game_and_retry_keeps_new_prefix(self):
        for name in ('Wow.exe', 'WTF/Config.wtf', 'Interface/AddOns/test.lua'):
            path = self.game / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'keep')
        with patch('core.macos_prefix.subprocess.run', return_value=Mock(returncode=0)) as run:
            self.migrate()
            self.assertFalse((self.prefix / 'old.reg').exists())
            self.assertEqual((self.prefix / RUNTIME_MARKER).read_text().strip(), RUNTIME_ID)
            (self.prefix / 'partial-install').write_bytes(b'retry')
            self.migrate()
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][-1], '-w')
            self.assertEqual((self.prefix / 'partial-install').read_bytes(), b'retry')
        for name in ('Wow.exe', 'WTF/Config.wtf', 'Interface/AddOns/test.lua'):
            self.assertEqual((self.game / name).read_bytes(), b'keep')

    def test_running_old_wine_is_not_removed(self):
        with patch('core.macos_prefix.subprocess.run', side_effect=subprocess.TimeoutExpired('wineserver', 3)):
            with self.assertRaisesRegex(RuntimeError, 'Закройте WoW'):
                self.migrate()
        self.assertTrue((self.prefix / 'old.reg').exists())

    def test_wrong_environment_or_runtime_cannot_remove_prefix(self):
        self.env['WINEPREFIX'] = str(self.game)
        with self.assertRaisesRegex(RuntimeError, 'Небезопасный'):
            self.migrate()
        self.env['WINEPREFIX'] = str(self.prefix)
        (self.resources / 'Wine/dreamworld-runtime-id').write_text('wrong')
        with self.assertRaisesRegex(RuntimeError, 'Версия'):
            self.migrate()
        self.assertTrue((self.prefix / 'old.reg').exists())

    @unittest.skipIf(os.name == 'nt', 'Проверка macOS/POSIX ссылок')
    def test_prefix_symlink_rejected_and_inner_links_do_not_delete_targets(self):
        outside = self.game / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('safe')
        (self.prefix / 'z-drive').symlink_to(outside, target_is_directory=True)
        with patch('core.macos_prefix.subprocess.run', return_value=Mock(returncode=0)):
            self.migrate()
        self.assertEqual((outside / 'keep').read_text(), 'safe')
        (self.prefix / RUNTIME_MARKER).unlink()
        self.prefix.rmdir()
        self.prefix.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'Небезопасный'):
            self.migrate()
        self.assertEqual((outside / 'keep').read_text(), 'safe')

    @unittest.skipIf(os.name == 'nt', 'Блокировка macOS/POSIX')
    def test_concurrent_launcher_refused_and_lock_released_after_failure(self):
        with self.assertRaisesRegex(ValueError, 'interrupted'):
            with prefix_lock(self.game):
                with self.assertRaisesRegex(RuntimeError, 'Другой лаунчер'):
                    with prefix_lock(self.game):
                        self.fail('second lock acquired')
                raise ValueError('interrupted')
        with prefix_lock(self.game):
            pass
