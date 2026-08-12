import unittest
from unittest.mock import Mock

from ui.main_window import MainWindow


class BootstrapUpdateFlowTests(unittest.TestCase):
    def test_detected_update_starts_automatically_before_play_is_enabled(self):
        window = Mock()
        window.worker = Mock()
        window.start_update = Mock()
        window._set_play_mode = Mock()

        MainWindow._on_post_bootstrap_check_done(window, True)

        self.assertIsNone(window.worker)
        window.start_update.assert_called_once_with()
        window._set_play_mode.assert_not_called()

    def test_play_is_enabled_only_after_clean_post_bootstrap_check(self):
        window = Mock()
        window.btn_play = Mock()
        window.progress_widget = Mock()
        window._set_play_mode = Mock()
        window._refresh_info = Mock()

        MainWindow._on_post_bootstrap_check_done(window, False)

        window.btn_play.setVisible.assert_called_once_with(True)
        window._set_play_mode.assert_called_once_with(True)
        window.progress_widget.set_status.assert_called_once_with(
            "Клиент актуален. Обновлений нет.", 100
        )


if __name__ == "__main__":
    unittest.main()
