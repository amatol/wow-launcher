import tempfile
import unittest
from pathlib import Path

from tools.generate_manifest import build_manifest


class GenerateManifestTests(unittest.TestCase):
    def test_builds_sorted_manifest_and_excludes_launcher_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Data").mkdir()
            (root / "Data" / "patch.MPQ").write_bytes(b"patch")
            (root / "Wow.exe").write_bytes(b"wow")
            (root / "Dreamworld.exe").write_bytes(b"launcher")
            (root / "Repair.log").write_text("local state")
            (root / ".launcher_version").write_text("old")
            result = build_manifest(root, "20260731", "https://example.test/launcher/")
            self.assertEqual([item["path"] for item in result["files"]], ["Data/patch.MPQ", "Wow.exe"])
            self.assertEqual(result["files"][0]["http_url"], "https://example.test/launcher/files/Data/patch.MPQ")

    def test_lists_files_removed_since_previous_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Wow.exe").write_bytes(b"wow")
            previous = {"files": [{"path": "Wow.exe"}, {"path": "Interface/AddOns/Old/Old.toc"}]}
            result = build_manifest(root, "20260808", "https://example.test", previous)
            self.assertEqual(result["removed_files"], ["Interface/AddOns/Old/Old.toc"])

    def test_carries_tombstones_forward_for_clients_that_skip_a_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Wow.exe").write_bytes(b"wow")
            previous = {
                "files": [{"path": "Wow.exe"}],
                "removed_files": ["Interface/AddOns/DreamQuestMap/README.md"],
            }

            result = build_manifest(root, "20260814", "https://example.test", previous)

            self.assertEqual(
                result["removed_files"],
                ["Interface/AddOns/DreamQuestMap/README.md"],
            )

    def test_drops_tombstone_when_path_is_published_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            readme = root / "Interface/AddOns/DreamQuestMap/README.md"
            readme.parent.mkdir(parents=True)
            readme.write_text("published again")
            previous = {
                "files": [],
                "removed_files": ["Interface/AddOns/DreamQuestMap/README.md"],
            }

            result = build_manifest(root, "20260814", "https://example.test", previous)

            self.assertEqual(result["removed_files"], [])


if __name__ == "__main__":
    unittest.main()
