import os
import sys
import tempfile
import unittest
from unittest import mock

from core.self_update import (
    _clean_pyinstaller_environment, _compare_versions, _move_exe,
    cleanup_self_update_files, wait_for_update_parent,
)


class SelfUpdateTests(unittest.TestCase):
    def test_self_update_does_not_install_companion_from_legacy_manifest(self):
        from pathlib import Path
        from core.self_update import download_update
        manifest = {"download_url": "https://example.test/launcher",
                    "size": 3, "sha256": "unused", "launchers": {
                        "windows": {"size": 100}, "macos": {"size": 200}}}
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                def download(**kwargs):
                    Path(kwargs["dest_path"]).write_bytes(b"new")
                    kwargs["progress_cb"](3, 3, "готово")
                    return True, ""
                progress = mock.Mock()
                with mock.patch("core.self_update.sys.platform", platform), \
                        mock.patch("core.self_update.tempfile.mkdtemp", return_value=directory), \
                        mock.patch("updater.net_utils.download_with_retries", side_effect=download) as fetch, \
                        mock.patch("core.launcher_bundle.sync_companion", side_effect=RuntimeError("недоступно")) as companion:
                    ok, path = download_update(manifest, progress)
                self.assertTrue(ok)
                self.assertEqual(Path(path).read_bytes(), b"new")
                fetch.assert_called_once()
                progress.assert_called_once_with(3, 3, "готово")
                companion.assert_not_called()

    def test_daily_release_is_newer_than_previous_day(self):
        self.assertGreater(_compare_versions("20260802", "20260801"), 0)

    def test_daily_release_migrates_from_legacy_ten_digit_version(self):
        self.assertGreater(_compare_versions("20260802", "2026080101"), 0)

    def test_bridge_manifest_matches_embedded_daily_version(self):
        self.assertEqual(_compare_versions("2026080200", "20260802"), 0)

    def test_cleanup_removes_old_and_bat_and_log(self):
        with tempfile.TemporaryDirectory() as game_dir:
            from config import Config
            old_exe = os.path.join(game_dir, Config.LAUNCHER_EXE_NAME + ".old")
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

    def test_move_exe_keeps_installed_copy_if_source_remove_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "Dreamworld.exe.new")
            destination = os.path.join(directory, "Dreamworld.exe")
            with open(source, "wb") as handle:
                handle.write(b"new launcher")

            with mock.patch("shutil.move", side_effect=OSError("move blocked")), \
                    mock.patch("os.remove", side_effect=PermissionError("locked")):
                _move_exe(source, destination)

            with open(destination, "rb") as handle:
                self.assertEqual(handle.read(), b"new launcher")
            self.assertTrue(os.path.isfile(source))

    def test_restart_environment_does_not_reuse_old_pyinstaller_runtime(self):
        with mock.patch.dict(os.environ, {
            "_PYI_APPLICATION_HOME_DIR": r"C:\\Temp\\_MEIold",
            "_MEIPASS2": r"C:\\Temp\\_MEIold",
        }):
            env = _clean_pyinstaller_environment()

        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", env)
        self.assertNotIn("_MEIPASS2", env)

    def test_update_restart_wait_argument_is_removed_before_qt(self):
        argv = ["Dreamworld.exe", "--self-update-parent-pid", "123", "other"]
        with mock.patch("core.self_update.sys.platform", "win32"), \
                mock.patch("core.self_update._wait_for_windows_process") as wait:
            self.assertTrue(wait_for_update_parent(argv, timeout_ms=5000))

        self.assertEqual(argv, ["Dreamworld.exe", "other"])
        wait.assert_called_once_with(123, 5000)

    def test_cleanup_keeps_recent_update_and_unrelated_temp_directory(self):
        with tempfile.TemporaryDirectory() as temp_root, tempfile.TemporaryDirectory() as game_dir:
            recent_update = os.path.join(temp_root, "dreamworld_update_active")
            unrelated = os.path.join(temp_root, "dreamworld_other_operation")
            os.makedirs(recent_update)
            os.makedirs(unrelated)

            from config import Config
            with mock.patch.object(Config, "GAME_DIR", game_dir), \
                    mock.patch("tempfile.gettempdir", return_value=temp_root):
                cleanup_self_update_files()

            self.assertTrue(os.path.isdir(recent_update))
            self.assertTrue(os.path.isdir(unrelated))


if __name__ == "__main__":
    unittest.main()
