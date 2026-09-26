import tempfile
import unittest
import zipfile
from pathlib import Path

from updater.bootstrap import BootstrapInstaller


class BootstrapInstallerTests(unittest.TestCase):
    def test_resume_keeps_partial_from_same_source(self):
        with tempfile.TemporaryDirectory() as directory:
            installer = BootstrapInstaller(directory)
            archive = Path(directory) / installer.ARCHIVE_NAME
            installer._prepare_archive("https://disk.yandex.ru/d/new", 100, archive)
            archive.write_bytes(b"partial")
            installer._prepare_archive("https://disk.yandex.ru/d/new", 100, archive)
            self.assertEqual(archive.read_bytes(), b"partial")

    def test_changed_source_or_size_discards_old_partial(self):
        for new_url, new_size in [("https://disk.yandex.ru/d/new", 100),
                                  ("https://disk.yandex.ru/d/old", 200)]:
            with self.subTest(url=new_url, size=new_size), tempfile.TemporaryDirectory() as directory:
                installer = BootstrapInstaller(directory)
                archive = Path(directory) / installer.ARCHIVE_NAME
                installer._prepare_archive("https://disk.yandex.ru/d/old", 100, archive)
                archive.write_bytes(b"old partial")
                installer._prepare_archive(new_url, new_size, archive)
                self.assertFalse(archive.exists())

    def test_legacy_or_invalid_source_discards_unidentified_partial(self):
        for metadata in [None, "invalid JSON"]:
            with self.subTest(metadata=metadata), tempfile.TemporaryDirectory() as directory:
                installer = BootstrapInstaller(directory)
                archive = Path(directory) / installer.ARCHIVE_NAME
                archive.write_bytes(b"old partial")
                if metadata is not None:
                    (Path(directory) / installer.SOURCE_NAME).write_text(metadata)
                installer._prepare_archive("https://disk.yandex.ru/d/new", 100, archive)
                self.assertFalse(archive.exists())

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
