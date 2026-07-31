"""
Главное окно лаунчера.
"""
import os
import sys

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QInputDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont

from config import Config
from core.version import check_wow_executable, launch_wow, get_current_version, set_current_version
from updater.manifest import Manifest, filter_needed, compute_needed_files
from updater.http_updater import HTTPUpdater
from ui.widgets import LogWidget, ProgressWidget


class UpdateWorker(QThread):
    """Рабочий поток обновления."""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str, int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, game_dir: str, manifest_url: str):
        super().__init__()
        self.game_dir = game_dir
        self.manifest_url = manifest_url
        self._cancel = False
        self._updater = None

    def cancel(self):
        self._cancel = True
        if self._updater:
            self._updater.cancel()

    def _progress_cb(self, current, total, downloaded, file_total, msg):
        percent = -1
        if total > 0:
            base = (current / total) * 100
            if file_total > 0:
                base += (downloaded / file_total) * (100 / total)
            percent = int(base)
        self.progress_signal.emit(msg, percent)
        self.log_signal.emit(msg)

    def run(self):
        try:
            self.log_signal.emit("Загрузка манифеста...")
            manifest = Manifest.fetch(self.manifest_url)
            self.log_signal.emit(f"Манифест: версия {manifest.version}, файлов: {len(manifest.files)}")

            current = Config.get_current_version()
            needed = filter_needed(manifest, current)

            if not needed:
                # Точечная проверка хэшей
                needed = compute_needed_files(manifest, self.game_dir)

            if not needed:
                self.finished_signal.emit(True, "Обновлений нет. Клиент актуален.")
                return

            self.log_signal.emit(f"Нужно обновить: {len(needed)} файлов")

            # Попытка HTTP
            self.log_signal.emit("Попытка HTTP-обновления...")
            self._updater = HTTPUpdater(self.game_dir, manifest, self._progress_cb)
            ok, count = self._updater.apply_all(needed)

            if ok:
                set_current_version(manifest.version)
                self.finished_signal.emit(True, f"Обновление завершено. Обновлено файлов: {count}")
                return

            if self._cancel:
                self.finished_signal.emit(False, "Обновление отменено.")
                return

            self.log_signal.emit("HTTP не удалось. Попытка BitTorrent...")

            if not Config.TORRENT_FALLBACK:
                self.finished_signal.emit(False, f"HTTP не удалось. Torren fallback отключён.")
                return

            try:
                from updater.torrent_updater import TorrentUpdater
                self._updater = TorrentUpdater(self.game_dir, manifest, self._progress_cb)
                ok_t, count_t = self._updater.apply_all(needed)
                if ok_t:
                    set_current_version(manifest.version)
                    self.finished_signal.emit(True, f"Обновление через торрент. Файлов: {count_t}")
                else:
                    self.finished_signal.emit(False, f"Торрент тоже не удалось. Файлов: {count_t}")
            except ImportError:
                self.finished_signal.emit(False, "libtorrent не установлен — torrent фолбэк недоступен.")
            except Exception as e:
                self.finished_signal.emit(False, f"Ошибка торрента: {e}")

        except Exception as e:
            self.finished_signal.emit(False, f"Ошибка: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dreamworld Launcher")
        self.setFixedSize(520, 520)
        self.worker = None

        self._apply_dark_theme()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # Заголовок
        title = QLabel("Dreamworld Launcher")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #e94560;")
        layout.addWidget(title)

        # Инфо
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        layout.addWidget(self.info_label)

        # Прогресс
        self.progress_widget = ProgressWidget()
        layout.addWidget(self.progress_widget)

        # Лог
        self.log_widget = LogWidget()
        layout.addWidget(self.log_widget, stretch=1)

        # Кнопки
        btn_layout = QHBoxLayout()

        self.btn_update = QPushButton("Обновить")
        self.btn_update.setFixedHeight(40)
        self.btn_update.clicked.connect(self.start_update)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_update)

        self.btn_play = QPushButton("Играть")
        self.btn_play.setFixedHeight(40)
        self.btn_play.clicked.connect(self.play)

        self.btn_settings = QPushButton("Настройки")
        self.btn_settings.setFixedHeight(40)
        self.btn_settings.clicked.connect(self.open_settings)

        btn_layout.addWidget(self.btn_update)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_settings)

        layout.addLayout(btn_layout)

        self._refresh_info()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #0f0f23; }
            QWidget { color: #e0e0e0; }
            QPushButton {
                background: #16213e; border: 1px solid #0f3460;
                border-radius: 5px; padding: 6px 16px; font-size: 13px;
            }
            QPushButton:hover { background: #0f3460; }
            QPushButton:pressed { background: #1a1a4e; }
            QPushButton:disabled { background: #1a1a2e; color: #555; }
        """)

    def _refresh_info(self):
        exe_found = check_wow_executable()
        version = get_current_version()
        exe_status = "Wow.exe найден" if exe_found else "Wow.exe НЕ найден"
        self.info_label.setText(
            f"Папка: {Config.GAME_DIR}\n"
            f"Версия патча: {version} | {exe_status}"
        )

    def start_update(self):
        if self.worker and self.worker.isRunning():
            return
        self.log_widget.log("=== Начало обновления ===")
        self.progress_widget.reset()
        self.btn_update.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_play.setEnabled(False)

        self.worker = UpdateWorker(Config.GAME_DIR, Config.MANIFEST_URL)
        self.worker.log_signal.connect(self.log_widget.log)
        self.worker.progress_signal.connect(self.progress_widget.set_status)
        self.worker.finished_signal.connect(self.on_update_finished)
        self.worker.start()

    def cancel_update(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log_widget.log("Отмена...")

    def on_update_finished(self, success: bool, message: str):
        self.log_widget.log(message)
        self.progress_widget.set_status(
            message, 100 if success else 0
        )
        self.btn_update.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_play.setEnabled(True)
        self._refresh_info()

    def play(self):
        if not check_wow_executable():
            QMessageBox.warning(self, "Ошибка", "Wow.exe не найден в папке лаунчера!")
            return
        self.log_widget.log("Запуск WoW...")
        launch_wow()
        self.close()

    def open_settings(self):
        text, ok = QInputDialog.getText(
            self, "URL манифеста", "Введите URL манифеста обновлений:",
            text=Config.MANIFEST_URL
        )
        if ok and text:
            Config.MANIFEST_URL = text
            self.log_widget.log(f"URL манифеста изменён: {text}")
