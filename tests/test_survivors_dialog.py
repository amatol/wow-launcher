"""Вход обязателен; отказ или отмена не должны запускать игру."""
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QLineEdit
from core.wow_auth import AuthError
from ui.survivors_dialog import SurvivorsWorker, SurvivorsDialog


class SurvivorsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_failed_login_never_installs_or_returns_launch(self):
        worker = SurvivorsWorker('user', 'secret', '', '/tmp/unused')
        with patch('ui.survivors_dialog.authenticate', side_effect=AuthError('Неверный логин или пароль.')), patch('ui.survivors_dialog.SurvivorsInstaller') as installer:
            worker.run()
        installer.assert_not_called()
        self.assertIsNone(worker.result)
        self.assertEqual(worker.password, '')
        self.assertEqual(worker.error, 'Неверный логин или пароль.')

    def test_success_installs_before_returning_launch(self):
        worker = SurvivorsWorker('user', 'secret', '', '/tmp/unused')
        with patch('ui.survivors_dialog.authenticate', return_value='USER') as auth, patch('ui.survivors_dialog.SurvivorsInstaller') as installer:
            installer.return_value.install.return_value = '/tmp/mode'
            worker.run()
        auth.assert_called_once()
        self.assertEqual(worker.result, ('/tmp/mode', 'USER'))
        self.assertIsNone(worker.error)
        self.assertEqual(worker.password, '')

    def test_long_install_rechecks_credentials(self):
        worker = SurvivorsWorker('user', 'secret', '', '/tmp/unused')
        with patch('ui.survivors_dialog.authenticate', side_effect=['USER', AuthError('Аккаунт заблокирован.')]) as auth, patch('ui.survivors_dialog.SurvivorsInstaller'), patch('ui.survivors_dialog.time.monotonic', side_effect=[0, 61]):
            worker.run()
        self.assertEqual(auth.call_count, 2)
        self.assertIsNone(worker.result)
        self.assertEqual(worker.password, '')

    def test_dialog_clears_password_before_starting_thread(self):
        dialog = SurvivorsDialog()
        self.addCleanup(dialog.deleteLater)
        dialog.username.setText('USER')
        dialog.password.setText('secret')
        self.assertEqual(dialog.password.echoMode(), QLineEdit.Password)
        with patch.object(SurvivorsWorker, 'start'):
            dialog.start()
        self.assertEqual(dialog.password.text(), '')
        self.assertFalse(dialog.play.isEnabled())
        dialog.worker.password = ''

    def test_cancel_running_worker_keeps_dialog_alive_until_finished(self):
        dialog = SurvivorsDialog()
        self.addCleanup(dialog.deleteLater)
        worker = MagicMock()
        worker.isRunning.return_value = True
        dialog.worker = worker
        dialog.reject()
        worker.requestInterruption.assert_called_once()
        self.assertTrue(dialog._close_pending)
        self.assertFalse(dialog.cancel.isEnabled())


if __name__ == '__main__':
    unittest.main()
