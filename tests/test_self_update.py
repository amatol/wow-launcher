import os
import sys
import tempfile
import unittest

from core.self_update import _compare_versions, cleanup_self_update_files


class SelfUpdateTests(unittest.TestCase):
    def test_daily_release_is_newer_than_previous_day(self):
        self.assertGreater(_compare_versions("20260802", "20260801"), 0)

    def test_daily_release_migrates_from_legacy_ten_digit_version(self):
        self.assertGreater(_compare_versions("20260802", "2026080101"), 0)

    def test_bridge_manifest_matches_embedded_daily_version(self):
        self.assertEqual(_compare_versions("2026080200", "20260802"), 0)

    def test_cleanup_removes_old_and_bat_and_log(self):
        with tempfile.TemporaryDirectory() as game_dir:
            old_exe = os.path.join(game_dir, "Dreamworld.exe.old")
            bat = os.path.join(game_dir, ".dreamworld_updater.bat")
            log = os.path.join(game_dir, ".dreamworld_updater.log")

            for p in (old_exe, bat, log):
                with open(p, "w") as f:
                    f.write("test")

            from config import Config
            orig_game_dir = Config.GAME_DIR
            Config.GAME_DIR = game_dir
            try:
                cleanup_self_update_files()
                for p in (old_exe, bat, log):
                    self.assertFalse(os.path.isfile(p), f"{p} should be removed")
            finally:
                Config.GAME_DIR = orig_game_dir

    def test_cleanup_removes_old_launcher_tmp(self):
        with tempfile.TemporaryDirectory() as game_dir:
            tmp = os.path.join(game_dir, ".launcher_tmp")
            os.makedirs(tmp)
            with open(os.path.join(tmp, "junk.part"), "w") as f:
                f.write("x")

            from config import Config
            orig_game_dir = Config.GAME_DIR
            Config.GAME_DIR = game_dir
            try:
                cleanup_self_update_files()
                self.assertFalse(os.path.isdir(tmp), ".launcher_tmp should be removed")
            finally:
                Config.GAME_DIR = orig_game_dir


if __name__ == "__main__":
    unittest.main()
