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


if __name__ == "__main__":
    unittest.main()
