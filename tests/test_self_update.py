import unittest

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


if __name__ == "__main__":
    unittest.main()
