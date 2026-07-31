import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from core.self_update import _build_updater_script, _compare_versions


class SelfUpdateTests(unittest.TestCase):
    def test_new_daily_release_is_newer(self):
        self.assertGreater(_compare_versions("2026080101", "20260731"), 0)
        self.assertGreater(_compare_versions("2026080101", "2026073101"), 0)

    def test_updater_script_only_moves_launcher_and_never_deletes(self):
        script = _build_updater_script(
            current_exe=r"C:\Games\WoW\Dreamworld.exe",
            new_exe_path=r"C:\Games\WoW\.launcher_tmp\Dreamworld.exe.new",
            log_path=r"C:\Games\WoW\.dreamworld_updater.log",
            pid=1234,
        )

        self.assertIn(
            'move /y "%NEW%" "%EXE%"',
            script,
        )
        self.assertIn('set "PYINSTALLER_RESET_ENVIRONMENT=1"', script)
        self.assertIn('set "_PYI_APPLICATION_HOME_DIR="', script)
        self.assertNotIn("\ndel ", script.lower())
        self.assertNotIn("*", script)
        self.assertNotIn("rmdir", script.lower())
        self.assertNotIn("rd /", script.lower())

    @unittest.skipUnless(sys.platform == "win32", "интеграционный тест Windows BAT")
    def test_windows_script_preserves_unrelated_client_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            current = root / "Dreamworld.exe"
            update_dir = root / ".launcher_tmp"
            update_dir.mkdir()
            new = update_dir / "Dreamworld.exe.new"
            log = root / ".dreamworld_updater.log"
            sentinel = root / "Wow.exe"
            data_file = root / "Data" / "client-data.bin"
            data_file.parent.mkdir()

            shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "where.exe", current)
            shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "whoami.exe", new)
            expected = new.read_bytes()
            sentinel.write_bytes(b"wow-client-sentinel")
            data_file.write_bytes(b"client-data-sentinel")

            finished = subprocess.Popen(["cmd.exe", "/d", "/c", "exit", "0"])
            finished.wait(timeout=10)
            script = _build_updater_script(
                str(current), str(new), str(log), finished.pid
            )
            bat = root / ".dreamworld_updater.bat"
            bat.write_text(script, encoding="utf-8")

            subprocess.run(
                ["cmd.exe", "/d", "/c", str(bat)],
                cwd=root,
                check=True,
                timeout=30,
            )

            self.assertEqual(current.read_bytes(), expected)
            self.assertFalse(new.exists())
            self.assertEqual(sentinel.read_bytes(), b"wow-client-sentinel")
            self.assertEqual(data_file.read_bytes(), b"client-data-sentinel")
            self.assertTrue(bat.exists())
            # START асинхронный; дать короткоживущему whoami.exe завершиться,
            # прежде чем TemporaryDirectory удалит тестовый каталог.
            time.sleep(1)


if __name__ == "__main__":
    unittest.main()
