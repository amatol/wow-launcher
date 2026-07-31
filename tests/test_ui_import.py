import unittest


class UiImportTests(unittest.TestCase):
    def test_main_window_module_imports(self):
        from ui.main_window import MainWindow

        self.assertEqual(MainWindow.__name__, "MainWindow")


if __name__ == "__main__":
    unittest.main()
