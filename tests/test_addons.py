import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from config import Config
from tools.generate_addons_manifest import package_addon
from updater.addons import AddonEntry, _validated_zip_members, fetch_addons_manifest


class _Response:
    def __init__(self, data): self._data = data
    def raise_for_status(self): pass
    def json(self): return self._data


class AddonsTests(unittest.TestCase):
    def test_manifest_rejects_unsafe_or_unverified_entries(self):
        base = {"name": "../Data", "version": "1", "download_url": "https://example/a.zip", "size": 1, "sha256": "a" * 64}
        with patch("updater.addons.requests.get", return_value=_Response({"addons": [base]})):
            self.assertIsNone(fetch_addons_manifest())
        base["name"] = "SafeAddon"
        base["sha256"] = ""
        with patch("updater.addons.requests.get", return_value=_Response({"addons": [base]})):
            self.assertIsNone(fetch_addons_manifest())

    def test_zip_rejects_traversal_and_wrong_top_level(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory, "bad.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("Addon/../../Data/file", b"bad")
            with zipfile.ZipFile(archive) as zf, self.assertRaises(ValueError):
                _validated_zip_members(zf, "Addon")

    def test_generator_packages_top_level_folder_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            addon = root / "MyAddon"
            addon.mkdir()
            (addon / "MyAddon.toc").write_text("## Interface: 30300", encoding="utf-8")
            entry = package_addon(addon, root / "out", "1.2.3", "https://example/addons")
            archive = root / "out" / "MyAddon-1.2.3.zip"
            self.assertEqual(entry["size"], archive.stat().st_size)
            self.assertEqual(entry["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            with zipfile.ZipFile(archive) as zf:
                self.assertIn("MyAddon/MyAddon.toc", zf.namelist())


if __name__ == "__main__":
    unittest.main()
