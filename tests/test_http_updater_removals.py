import tempfile
import unittest
from pathlib import Path

from updater.http_updater import HTTPUpdater
from updater.manifest import Manifest


class HTTPUpdaterRemovalTests(unittest.TestCase):
    def test_removes_listed_files_but_preserves_unlisted_user_files(self):
        with tempfile.TemporaryDirectory() as directory:
            addon = Path(directory, "Interface", "AddOns", "Old")
            addon.mkdir(parents=True)
            obsolete = addon / "Old.toc"
            custom = addon / "user-note.txt"
            obsolete.write_bytes(b"old")
            custom.write_bytes(b"keep")
            manifest = Manifest.from_dict({
                "version": "20260808", "files": [],
                "removed_files": ["Interface/AddOns/Old/Old.toc"],
            })

            self.assertEqual(HTTPUpdater(directory, manifest).apply_all([]), (True, 0))
            self.assertFalse(obsolete.exists())
            self.assertTrue(custom.exists())

    def test_removes_empty_addon_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            obsolete = Path(directory, "Interface", "AddOns", "Old", "Old.toc")
            obsolete.parent.mkdir(parents=True)
            obsolete.write_bytes(b"old")
            manifest = Manifest.from_dict({
                "version": "20260808", "files": [],
                "removed_files": ["Interface/AddOns/Old/Old.toc"],
            })

            HTTPUpdater(directory, manifest).apply_all([])
            self.assertFalse(obsolete.parent.exists())


if __name__ == "__main__":
    unittest.main()
