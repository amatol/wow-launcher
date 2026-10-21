"""Вход, установка и запуск отдельного режима без блокировки интерфейса."""
import time

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar,
)

from config import Config
from core.survivors import SurvivorsInstaller, Cancelled, launch_survivors
from core.wow_auth import authenticate, AuthError
from ui.theme import STYLESHEET


class SurvivorsWorker(QThread):
    progress = pyqtSignal(str, int)

    def __init__(self, username, password, token, game_dir, parent=None):
        super().__init__(parent)
        self.username, self.password, self.token = username, password, token
        self.game_dir = game_dir
        self.result = None
        self.error = None

    def run(self):
        try:
            self.progress.emit('Проверка аккаунта Dreamworld…', -1)
            username = authenticate(self.username, self.password, Config.AUTH_HOST, Config.AUTH_PORT, token=self.token)
            checked_at = time.monotonic()
            installer = SurvivorsInstaller(self.game_dir, self.progress.emit, self.isInterruptionRequested)
            root = installer.install()
            if self.isInterruptionRequested():
                raise Cancelled('Запуск отменён.')
            # После долгой установки пароль мог измениться, а аккаунт — быть заблокирован.
            if time.monotonic() - checked_at > 60:
                self.progress.emit('Повторная проверка аккаунта перед запуском…', -1)
                username = authenticate(self.username, self.password, Config.AUTH_HOST, Config.AUTH_PORT, token=self.token)
            if self.isInterruptionRequested():
                raise Cancelled('Запуск отменён.')
            self.result = (root, username)
        except (AuthError, Cancelled, ValueError, OSError) as error:
            self.error = str(error)
        except Exception:
            self.error = 'Не удалось получить файлы режима. Проверьте подключение и повторите попытку.'
        finally:
            self.password = self.token = ''


class SurvivorsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Warcraft Survivors')
        self.setMinimumSize(480, 400)
        self.resize(520, 430)
        self.setStyleSheet(STYLESHEET + '''
            QLineEdit { background: #102331; border: 1px solid #395263;
                border-radius: 4px; padding: 8px; color: #e4edf2; }
            QLineEdit:focus { border: 2px solid #b9e8f7; }
        ''')
        self.worker = None
        self.process = None
        self._close_pending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel('Warcraft Survivors')
        title.setStyleSheet('font-size: 22px; color: #ddba7c;')
        layout.addWidget(title)
        description = QLabel('Одиночные сражения с волнами врагов.\nВойдите с логином и паролем вашего аккаунта Dreamworld.')
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.username = QLineEdit()
        self.username.setMaxLength(32)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMaxLength(32)
        self.token = QLineEdit()
        self.token.setMaxLength(6)
        self.token.setPlaceholderText('Если включён на аккаунте')
        form.addRow('Логин', self.username)
        form.addRow('Пароль', self.password)
        form.addRow('Код аутентификатора', self.token)
        layout.addLayout(form)
        note = QLabel('При первом запуске скачаются отдельные данные WoW 1.12.1.\nПароль не сохраняется. Прогресс WoW остаётся отдельным.')
        note.setWordWrap(True)
        note.setStyleSheet('color: #b7cedd; font-size: 12px;')
        layout.addWidget(note)
        self.status = QLabel('Готово к входу.')
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(38)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        buttons = QHBoxLayout()
        self.cancel = QPushButton('Закрыть')
        self.cancel.clicked.connect(self.reject)
        self.play = QPushButton('Войти и играть')
        self.play.setProperty('role', 'primary')
        self.play.setDefault(True)
        self.play.clicked.connect(self.start)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.play)
        layout.addLayout(buttons)
        self.username.setFocus()

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.username.text().strip() or not self.password.text():
            self.status.setText('Введите логин и пароль вашего аккаунта Dreamworld.')
            (self.username if not self.username.text().strip() else self.password).setFocus()
            return
        self._close_pending = False
        self.worker = SurvivorsWorker(self.username.text(), self.password.text(), self.token.text(), Config.GAME_DIR, self)
        self.password.clear()
        self.token.clear()
        self._busy(True)
        self.cancel.setText('Отмена')
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _busy(self, busy):
        for widget in (self.username, self.password, self.token, self.play):
            widget.setEnabled(not busy)

    def _progress(self, message, percent):
        self.status.setText(message)
        self.bar.setRange(0, 0 if percent < 0 else 100)
        if percent >= 0:
            self.bar.setValue(percent)

    def _finished(self):
        self._busy(False)
        self.cancel.setText('Закрыть')
        self.cancel.setEnabled(True)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        if self._close_pending:
            super().reject()
            return
        if self.worker.error:
            self.status.setText(self.worker.error)
            self.password.setFocus()
            return
        try:
            self.process = launch_survivors(*self.worker.result)
        except OSError:
            self.status.setText('Не удалось запустить игру. Закройте её прежнее окно и попробуйте ещё раз.')
            return
        self.accept()

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self._close_pending = True
            self.cancel.setEnabled(False)
            self.status.setText('Остановка загрузки…')
            return
        self.password.clear()
        self.token.clear()
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.reject()
            event.ignore()
        else:
            self.password.clear()
            self.token.clear()
            event.accept()
