import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from updater.http_updater import HTTPUpdater
from updater.manifest import Manifest


class HTTPUpdaterStagingTests(unittest.TestCase):
    def test_staging_directory_is_on_client_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            game_dir = Path(directory) / "client"
            manifest = Manifest.from_dict({"version": "20260812", "files": []})
            updater = HTTPUpdater(str(game_dir), manifest)
            system_temp = Path(directory) / "system-temp"
            system_temp.mkdir()

            with patch("tempfile.gettempdir", return_value=str(system_temp)):
                staging = Path(updater._get_tmp_dir())

            self.assertEqual(staging.parent, game_dir)
            self.assertTrue(os.path.samefile(staging.parent, game_dir))
            updater.cleanup()


if __name__ == "__main__":
    unittest.main()
