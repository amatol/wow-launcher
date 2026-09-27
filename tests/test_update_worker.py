import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from ui.main_window import UpdateWorker
from updater.manifest import Manifest


class UpdateWorkerTests(unittest.TestCase):
    def check_update(self, outcome):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Wow.exe").write_bytes(b"client")
            (root / "Data").mkdir()
            (root / "Data/old.MPQ").write_bytes(b"obsolete")
            (root / ".launcher_version").write_text("20260926")
            manifest = Manifest.from_dict({
                "version": "20260927",
                "files": [
                    {"path": name, "size": 3,
                     "sha256": hashlib.sha256(b"new").hexdigest(),
                     "http_url": "https://example.invalid/" + name}
                    for name in ("Data/first.MPQ", "Data/second.MPQ")
                ],
                "removed_files": ["Data/old.MPQ"],
            })
            worker = UpdateWorker(directory, "https://example.invalid/manifest.json")
            results = []
            worker.finished_signal.connect(lambda ok, message: results.append((ok, message)))

            def download(**kwargs):
                if kwargs["url"].endswith("second.MPQ") and outcome != "success":
                    if outcome == "cancel":
                        worker.cancel()
                    return False, "Соединение прервано"
                Path(kwargs["dest_path"]).write_bytes(b"new")
                return True, ""

            with patch.object(Config, "GAME_DIR", directory), \
                    patch.object(Config, "VERSION_FILE", str(root / ".launcher_version")), \
                    patch.object(Config, "WOW_EXE", None), \
                    patch("ui.main_window.Manifest.fetch", return_value=manifest), \
                    patch("updater.http_updater.download_with_retries", side_effect=download) as fetch:
                worker.run()

            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], outcome == "success")
            self.assertEqual((root / "Data/first.MPQ").read_bytes(), b"new")
            self.assertEqual((root / "Data/second.MPQ").exists(), outcome == "success")
            self.assertEqual((root / "Data/old.MPQ").exists(), outcome != "success")
            self.assertEqual((root / ".launcher_version").read_text(),
                             "20260927" if outcome == "success" else "20260926")
            self.assertFalse(list(root.glob(".dw_dl_*")))
            return results[0][1]

    def test_success_commits_version_and_removes_obsolete_files(self):
        self.assertIn("Обновление завершено", self.check_update("success"))

    def test_partial_failure_preserves_version_and_obsolete_files(self):
        message = self.check_update("failure")
        self.assertIn("1 из 2", message)
        self.assertIn("повторите попытку", message)

    def test_cancel_preserves_version_and_obsolete_files(self):
        self.assertEqual(self.check_update("cancel"), "Обновление отменено.")


if __name__ == "__main__":
    unittest.main()
