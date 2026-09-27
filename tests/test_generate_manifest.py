import tempfile
import unittest
import json
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

from tools.generate_manifest import build_manifest, main


class GenerateManifestTests(unittest.TestCase):
    def test_cli_uses_moscow_release_day_after_utc_midnight_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "client"
            source.mkdir()
            (source / "Wow.exe").write_bytes(b"wow")
            output = root / "manifest.json"
            instant = datetime(2026, 9, 26, 21, 30, tzinfo=timezone.utc)
            with patch("tools.generate_manifest.datetime") as clock, patch(
                "sys.argv", ["generate_manifest.py", str(source), str(output)]
            ):
                clock.now.side_effect = lambda tz: instant.astimezone(tz)
                main()
            self.assertEqual(json.loads(output.read_text())["version"], "20260927")

    def test_cli_rejects_old_release_date_without_overwriting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "manifest.json"
            output.write_text("previous manifest")
            with patch("tools.generate_manifest.datetime") as clock, patch(
                "sys.argv", ["generate_manifest.py", str(root), str(output), "--version", "20260920"]
            ), patch("sys.stderr"):
                clock.now.return_value = datetime(2026, 9, 27)
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(output.read_text(), "previous manifest")

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
