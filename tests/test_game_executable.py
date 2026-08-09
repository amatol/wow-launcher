import tempfile
import unittest
from pathlib import Path

from config import Config


class GameExecutableTests(unittest.TestCase):
    def test_launcher_is_not_detected_as_game(self):
        original_dir = Config.GAME_DIR
        original_exe = Config.WOW_EXE
        try:
            with tempfile.TemporaryDirectory() as directory:
                Config.GAME_DIR = directory
                Path(directory, "Dreamworld.exe").write_bytes(b"launcher")
                self.assertIsNone(Config.detect_wow_exe())
                wow = Path(directory, "Wow.exe")
                wow.write_bytes(b"client")
                self.assertEqual(Config.detect_wow_exe(), str(wow))
                self.assertFalse(Config.has_complete_client_layout())
                Path(directory, "Data").mkdir()
                self.assertTrue(Config.has_complete_client_layout())
                Path(directory, ".dreamworld_bootstrap_incomplete").touch()
                self.assertFalse(Config.has_complete_client_layout())
        finally:
            Config.GAME_DIR = original_dir
            Config.WOW_EXE = original_exe


if __name__ == "__main__":
    unittest.main()
