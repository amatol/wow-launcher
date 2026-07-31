import hashlib
import tempfile
import unittest
from pathlib import Path

from updater.manifest import Manifest, compute_needed_files


class ManifestTests(unittest.TestCase):
    def test_rejects_path_traversal(self):
        for path in ("../outside", "/absolute", "Data/../outside", "C:/Windows/file"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                Manifest.from_dict({"version": "20260731", "files": [{"path": path}]})

    def test_validates_version_and_hash(self):
        with self.assertRaises(ValueError):
            Manifest.from_dict({"version": "1.0.0", "files": []})
        with self.assertRaises(ValueError):
            Manifest.from_dict({"version": "20260731", "files": [{"path": "Wow.exe", "sha256": "bad"}]})

    def test_computes_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "Data", "patch.MPQ")
            path.parent.mkdir()
            path.write_bytes(b"ok")
            good_hash = hashlib.sha256(b"ok").hexdigest()
            manifest = Manifest.from_dict({"version": "20260731", "files": [{"path": "Data/patch.MPQ", "size": 2, "sha256": good_hash}]})
            self.assertEqual(compute_needed_files(manifest, directory), [])
            path.write_bytes(b"changed")
            self.assertEqual(len(compute_needed_files(manifest, directory)), 1)


if __name__ == "__main__":
    unittest.main()
