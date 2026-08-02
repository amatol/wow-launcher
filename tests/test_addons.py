import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.generate_addons_manifest import describe_addon
from updater.addons import AddonEntry, AddonFile, _validate_entry, fetch_addons_manifest, install_addon


class _Response:
    def __init__(self, data=None, content=b""):
        self._data = data
        self._content = content
        self.headers = {"Content-Length": str(len(content))}
    def raise_for_status(self): pass
    def json(self): return self._data
    def iter_content(self, chunk_size):
        yield self._content


class AddonsTests(unittest.TestCase):
    def test_manifest_rejects_unsafe_or_unverified_files(self):
        item = {"path": "../Data/file", "download_url": "https://example/file", "size": 1, "sha256": "a" * 64}
        base = {"name": "SafeAddon", "version": "1", "folders": ["SafeAddon"], "files": [item]}
        with patch("updater.addons.requests.get", return_value=_Response(base)):
            self.assertIsNone(fetch_addons_manifest())
        item["path"] = "file.lua"
        item["sha256"] = ""
        with patch("updater.addons.requests.get", return_value=_Response({"addons": [base]})):
            self.assertIsNone(fetch_addons_manifest())

    def test_generator_describes_directory_files(self):
        with tempfile.TemporaryDirectory() as directory:
            addon = Path(directory) / "MyAddon"
            addon.mkdir()
            toc = b"## Interface: 30300"
            (addon / "MyAddon.toc").write_bytes(toc)
            entry = describe_addon(addon, "1.2.3", "https://example/addons")
            self.assertEqual(entry["folders"], ["MyAddon"])
            self.assertEqual(entry["files"], [{
                "path": "MyAddon/MyAddon.toc",
                "download_url": "https://example/addons/MyAddon/MyAddon.toc",
                "sha256": hashlib.sha256(toc).hexdigest(),
                "size": len(toc),
            }])

    def test_install_downloads_verified_files_into_addon_directory(self):
        payload = b"## Interface: 30300"
        entry = _validate_entry(AddonEntry("MyAddon", "1", folders=["MyAddon"], files=[AddonFile(
            "MyAddon/MyAddon.toc", "https://example/MyAddon.toc", hashlib.sha256(payload).hexdigest(), len(payload)
        )]))
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(__import__("updater.addons", fromlist=["Config"]).Config, "ADDONS_DIR", str(Path(directory) / "AddOns")), \
             patch.object(__import__("updater.addons", fromlist=["Config"]).Config, "ADDONS_STATE_FILE", str(Path(directory) / ".launcher_addons")), \
             patch("updater.addons.requests.get", return_value=_Response(content=payload)):
            self.assertTrue(install_addon(entry))
            self.assertEqual((Path(directory) / "AddOns/MyAddon/MyAddon.toc").read_bytes(), payload)

    def test_generator_and_installer_support_multiple_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "DeadlyBossMods"
            core = package / "DBM-Core"
            gui = package / "DBM-GUI"
            core.mkdir(parents=True)
            gui.mkdir()
            core_payload = b"## Interface: 30300\nCore"
            gui_payload = b"## Interface: 30300\nGUI"
            (core / "DBM-Core.toc").write_bytes(core_payload)
            (gui / "DBM-GUI.toc").write_bytes(gui_payload)

            generated = describe_addon(package, "2", "https://example/addons")
            self.assertEqual(generated["folders"], ["DBM-Core", "DBM-GUI"])
            self.assertEqual(
                [item["path"] for item in generated["files"]],
                ["DBM-Core/DBM-Core.toc", "DBM-GUI/DBM-GUI.toc"],
            )

            entry = _validate_entry(AddonEntry(
                generated["name"], generated["version"], folders=generated["folders"],
                files=[AddonFile(**item) for item in generated["files"]],
            ))
            responses = {
                generated["files"][0]["download_url"]: _Response(content=core_payload),
                generated["files"][1]["download_url"]: _Response(content=gui_payload),
            }
            addons_dir = root / "client/AddOns"
            state_file = root / "client/.launcher_addons"
            with patch.object(__import__("updater.addons", fromlist=["Config"]).Config, "ADDONS_DIR", str(addons_dir)), \
                 patch.object(__import__("updater.addons", fromlist=["Config"]).Config, "ADDONS_STATE_FILE", str(state_file)), \
                 patch("updater.addons.requests.get", side_effect=lambda url, **kwargs: responses[url]):
                self.assertTrue(install_addon(entry))
                self.assertEqual((addons_dir / "DBM-Core/DBM-Core.toc").read_bytes(), core_payload)
                self.assertEqual((addons_dir / "DBM-GUI/DBM-GUI.toc").read_bytes(), gui_payload)
                self.assertIn('"folders": [', state_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
