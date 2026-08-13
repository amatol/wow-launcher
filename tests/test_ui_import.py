import unittest


class UiImportTests(unittest.TestCase):
    def test_main_window_module_imports(self):
        from ui.main_window import MainWindow

        self.assertEqual(MainWindow.__name__, "MainWindow")

    def test_main_window_uses_smaller_compact_geometry(self):
        from ui.main_window import MainWindow

        self.assertEqual(
            (MainWindow.DEFAULT_WIDTH, MainWindow.DEFAULT_HEIGHT),
            (1000, 560),
        )
        self.assertEqual(
            MainWindow.SETTINGS_GEOMETRY_KEY,
            "main_window/geometry_compact_v2",
        )


if __name__ == "__main__":
    unittest.main()
