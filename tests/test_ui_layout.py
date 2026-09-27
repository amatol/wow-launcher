"""Проверка доступности действий в компактном окне без сети и записи настроек."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.theme import ASSETS


class UiLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.patches = [
            patch("PyQt5.QtCore.QThread.start"),
            patch.object(MainWindow, "_restore_window_geometry"),
            patch("config.Config.has_complete_client_layout", return_value=True),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)

    def test_actions_fit_compact_window_with_long_status(self):
        window = self.window
        window.resize(720, 400)
        window._on_check_done(False)
        window.progress_widget.set_status("Data/" + "очень-длинный-путь/" * 30, 42)
        window.show()
        for _ in range(3):
            self.app.processEvents()
        self.assertEqual((window.width(), window.height()), (720, 400))
        for button in (window.btn_play, window.btn_addons, window.btn_account):
            bottom_right = button.mapTo(window, button.rect().bottomRight())
            self.assertTrue(window.rect().contains(bottom_right))
            self.assertTrue(window.rect().contains(button.mapTo(window, QPoint(0, 0))))
            self.assertLess(button.fontMetrics().horizontalAdvance(button.text()), button.width() - 20)
        self.assertEqual(window.progress_widget.percent_label.text(), "42%")
        self.assertGreater(window.news_widget.viewport().height(), 100)

    def test_primary_action_still_switches_between_play_and_update(self):
        with patch.object(self.window, "play") as play, patch.object(self.window, "start_update") as update:
            self.window._on_check_done(False)
            self.window.btn_play.click()
            play.assert_called_once()
            self.window._on_check_done(True)
            self.window.btn_play.click()
            update.assert_called_once()

    def test_visual_assets_are_available(self):
        self.assertFalse(self.window.centralWidget()._source.isNull())
        for name in ("fonts/Cinzel.ttf", "fonts/OFL-Cinzel.txt", "check.svg"):
            self.assertTrue((ASSETS / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
