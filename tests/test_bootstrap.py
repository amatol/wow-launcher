import tempfile
import unittest
import zipfile
from pathlib import Path

from updater.bootstrap import BootstrapInstaller


class BootstrapInstallerTests(unittest.TestCase):
    def test_finds_client_inside_single_top_level_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "World of Warcraft"
            (client / "Data").mkdir(parents=True)
            (client / "Wow.exe").write_bytes(b"wow")
            self.assertEqual(BootstrapInstaller._find_client_root(root), client)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                BootstrapInstaller._safe_member_path(Path(directory), "../Wow.exe")

    def test_extracts_safe_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "client.zip"
            staging = root / "staging"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("Client/Wow.exe", b"wow")
                output.writestr("Client/Data/file.bin", b"data")
            installer = BootstrapInstaller(str(root))
            installer._extract(archive, staging)
            self.assertEqual(installer._find_client_root(staging), staging / "Client")


if __name__ == "__main__":
    unittest.main()
