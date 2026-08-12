"""
Главное окно лаунчера.
"""
import os
import sys

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox,
    QProgressBar, QDialog, QApplication, QFrame
)
from PyQt5.QtCore import QSettings, QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtGui import QFont, QDesktopServices

from config import Config
from core.version import check_wow_executable, launch_wow, get_current_version, set_current_version
from core.self_update import (
    fetch_launcher_manifest, is_update_available,
    download_update, apply_update,
)
from updater.manifest import (
    Manifest, compute_existing_removed_files, filter_needed, remove_obsolete_files,
)
from updater.http_updater import HTTPUpdater
from updater.bootstrap import BootstrapInstaller
from ui.widgets import NewsWidget, NewsWorker, ProgressWidget
from ui.addons_dialog import AddonsDialog


class CheckWorker(QThread):
    """Фоновая проверка наличия обновлений клиента при запуске."""

    check_done = pyqtSignal(bool)  # True если есть обновления

    def run(self):
        if not Config.has_complete_client_layout():
            self.check_done.emit(True)
            return
        try:
            manifest = Manifest.fetch(Config.MANIFEST_URL)
            needed = filter_needed(manifest, Config.get_current_version(), Config.GAME_DIR)
            removed = compute_existing_removed_files(manifest, Config.GAME_DIR)
            self.check_done.emit(bool(needed or removed))
        except Exception:
            # При ошибке сети — считаем что обновлений нет, даём играть
            self.check_done.emit(False)


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
            if not Config.has_complete_client_layout():
                self.log_signal.emit("Скачивание базового клиента с Яндекс Диска...")
                self._updater = BootstrapInstaller(
                    self.game_dir,
                    lambda done, total, msg: self.progress_signal.emit(
                        msg, int(done * 100 / total) if total else -1
                    ),
                )
                ok, message = self._updater.install(Config.CLIENT_ARCHIVE_PUBLIC_URL)
                if not ok:
                    self.finished_signal.emit(False, message)
                    return
                self.log_signal.emit(message)

            self.log_signal.emit("Проверка файлов клиента...")
            manifest = Manifest.fetch(self.manifest_url)
            self.log_signal.emit(f"Манифест: версия {manifest.version}, файлов: {len(manifest.files)}")

            needed = filter_needed(manifest, Config.get_current_version(), self.game_dir)
            removed = compute_existing_removed_files(manifest, self.game_dir)

            if not needed and not removed:
                set_current_version(manifest.version)
                self.finished_signal.emit(True, "Клиент актуален. Обновлений нет.")
                return

            self.log_signal.emit(
                f"Нужно обновить: {len(needed)} из {len(manifest.files)} файлов; "
                f"удалить устаревших: {len(removed)}"
            )

            # Попытка HTTP
            self.log_signal.emit("HTTP-обновление...")
            self._updater = HTTPUpdater(self.game_dir, manifest, self._progress_cb)
            ok, count = self._updater.apply_all(needed)

            if ok:
                set_current_version(manifest.version)
                self.finished_signal.emit(
                    True, f"Обновление завершено. Обновлено файлов: {count}, удалено: {len(removed)}"
                )
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
                    remove_obsolete_files(manifest, self.game_dir)
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


class SelfUpdateWorker(QThread):
    """
    Фоновый поток проверки обновлений самого лаунчера.
    Тихий: если обновлений нет или ошибка сети — ничего не показывает.
    """

    update_available_signal = pyqtSignal(dict)  # манифест, если есть обновление
    download_progress_signal = pyqtSignal(int, int)  # downloaded, total
    download_finished_signal = pyqtSignal(bool, str)  # (успех, путь_к_файлу)

    def __init__(self):
        super().__init__()
        self._manifest = None
        self._download_mode = False

    def check_only(self):
        self._download_mode = False
        self.start()

    def download_and_apply(self, manifest: dict):
        self._manifest = manifest
        self._download_mode = True
        self.start()

    def run(self):
        if self._download_mode:
            self._do_download()
        else:
            self._do_check()

    def _do_check(self):
        manifest = fetch_launcher_manifest()
        if manifest is None:
            return
        if is_update_available(manifest):
            self.update_available_signal.emit(manifest)

    def _do_download(self):
        ok, path = download_update(
            self._manifest,
            progress_cb=lambda d, t, msg: self.download_progress_signal.emit(d, t),
        )
        self.download_finished_signal.emit(ok, path)


class SelfUpdateDialog(QDialog):
    """Диалог предложения обновить лаунчер."""

    def __init__(self, manifest: dict, parent=None):
        super().__init__(parent)
        self.manifest = manifest
        self.setWindowTitle("Доступно обновление лаунчера")
        self.setFixedSize(640, 340)
        self._apply_theme()

        layout = QVBoxLayout(self)

        remote_ver = manifest.get("version", "?")
        changelog = manifest.get("changelog", "")

        label = QLabel(
            f"Доступна новая версия лаунчера: {remote_ver}\n"
            f"Текущая версия: {Config.LAUNCHER_VERSION}"
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #e0e0e0; font-size: 20px;")
        layout.addWidget(label)

        if changelog:
            ch_label = QLabel(f"Что нового:\n{changelog}")
            ch_label.setStyleSheet("color: #a0a0a0; font-size: 17px;")
            ch_label.setWordWrap(True)
            layout.addWidget(ch_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        self.btn_yes = QPushButton("Обновить")
        self.btn_no = QPushButton("Позже")
        self.btn_yes.setFixedHeight(54)
        self.btn_no.setFixedHeight(54)
        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        layout.addLayout(btn_layout)

        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog { background: #0f0f23; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #16213e; border: 1px solid #0f3460;
                border-radius: 7px; padding: 10px 22px; font-size: 20px;
                color: #e0e0e0;
            }
            QPushButton:hover { background: #0f3460; }
            QProgressBar {
                background: #16213e; border: 1px solid #0f3460;
                border-radius: 4px; text-align: center; color: white;
            }
            QProgressBar::chunk { background: #0f3460; border-radius: 3px; }
        """)

    def set_progress(self, downloaded: int, total: int):
        self.progress_bar.setVisible(True)
        if total > 0:
            self.progress_bar.setValue(int(downloaded / total * 100))


class MainWindow(QMainWindow):
    DEFAULT_WIDTH = 1440
    DEFAULT_HEIGHT = 800
    MINIMUM_WIDTH = 720
    MINIMUM_HEIGHT = 400
    SETTINGS_GEOMETRY_KEY = "main_window/geometry"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dreamworld Launcher")
        self.setMinimumSize(self.MINIMUM_WIDTH, self.MINIMUM_HEIGHT)
        self.worker = None
        self.self_update_worker = None
        self.self_update_dialog = None
        self.news_worker = None
        self.check_worker = None

        self._apply_dark_theme()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        # --- Верхняя панель: заголовок + инфо ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(24)

        title = QLabel("Dreamworld")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet("color: #e94560;")
        title.setFixedHeight(56)

        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #a0a0a0; font-size: 18px;")
        self.info_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        top_bar.addWidget(title)
        top_bar.addStretch()
        top_bar.addWidget(self.info_label)
        outer.addLayout(top_bar)

        # --- Основная зона: новости слева, кнопки справа ---
        main_row = QHBoxLayout()
        main_row.setSpacing(24)

        # Новости
        self.news_widget = NewsWidget()
        main_row.addWidget(self.news_widget, stretch=1)

        # Правая колонка с кнопками
        right_panel = QFrame()
        right_panel.setFixedWidth(320)
        right_panel.setStyleSheet("QFrame { background: #16213e; border-radius: 12px; }")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(24, 24, 24, 24)
        right_layout.setSpacing(18)

        self.btn_play = QPushButton("Играть")
        self.btn_play.setFixedHeight(76)
        self.btn_play.setStyleSheet(
            "QPushButton { background: #e94560; border: none; border-radius: 5px; "
            "font-size: 24px; font-weight: bold; color: white; }"
            "QPushButton:hover { background: #ff5570; }"
            "QPushButton:pressed { background: #c81e3f; }"
            "QPushButton:disabled { background: #3a2a3a; color: #777; }"
        )
        self._play_mode = True
        self.btn_play.clicked.connect(self._on_play_clicked)

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setFixedHeight(76)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #e94560; border: none; border-radius: 5px; "
            "font-size: 24px; font-weight: bold; color: white; }"
            "QPushButton:hover { background: #ff5570; }"
            "QPushButton:pressed { background: #c81e3f; }"
        )
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.cancel_update)

        self.btn_addons = QPushButton("Аддоны")
        self.btn_addons.setFixedHeight(60)
        self.btn_addons.clicked.connect(self.open_addons)

        self.btn_account = QPushButton("Аккаунт")
        self.btn_account.setFixedHeight(52)
        self.btn_account.clicked.connect(self.open_account)

        right_layout.addWidget(self.btn_play)
        right_layout.addWidget(self.btn_cancel)
        right_layout.addSpacing(6)
        right_layout.addWidget(self.btn_addons)
        right_layout.addStretch()
        right_layout.addWidget(self.btn_account)

        main_row.addWidget(right_panel)
        outer.addLayout(main_row, stretch=1)

        # --- Прогресс-бар внизу ---
        self.progress_widget = ProgressWidget()
        outer.addWidget(self.progress_widget)

        self._restore_window_geometry()

        self._refresh_info()
        self._load_news()
        self._start_client_check()

        # Фоновая проверка обновлений лаунчера (тихая)
        self._start_self_update_check()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #0f0f23; }
            QWidget { color: #e0e0e0; }
            QPushButton {
                background: #16213e; border: 1px solid #0f3460;
                border-radius: 7px; padding: 10px 22px; font-size: 20px;
            }
            QPushButton:hover { background: #0f3460; }
            QPushButton:pressed { background: #1a1a4e; }
            QPushButton:disabled { background: #1a1a2e; color: #555; }
        """)

    def _restore_window_geometry(self):
        """Восстановить размер и монитор либо показать окно на основном экране."""
        saved_geometry = QSettings().value(self.SETTINGS_GEOMETRY_KEY)
        if saved_geometry and self.restoreGeometry(saved_geometry) and self._is_on_available_screen():
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
            return

        available = screen.availableGeometry()
        width = min(self.DEFAULT_WIDTH, max(self.MINIMUM_WIDTH, int(available.width() * 0.9)))
        height = min(self.DEFAULT_HEIGHT, max(self.MINIMUM_HEIGHT, int(available.height() * 0.9)))
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    def _is_on_available_screen(self):
        frame = self.frameGeometry()
        return any(frame.intersects(screen.availableGeometry()) for screen in QApplication.screens())

    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue(self.SETTINGS_GEOMETRY_KEY, self.saveGeometry())
        settings.sync()
        super().closeEvent(event)

    def _refresh_info(self):
        exe_found = check_wow_executable()
        client_version = get_current_version()
        exe_status = "Wow.exe найден" if exe_found else "Wow.exe НЕ найден"
        self.info_label.setText(
            f"Лаунчер: {Config.LAUNCHER_VERSION}  |  Клиент: {client_version}  |  {exe_status}"
        )

    def _load_news(self):
        """Запустить фоновую загрузку новостей сервера."""
        self.news_worker = NewsWorker()
        self.news_worker.news_signal.connect(self._on_news_loaded)
        self.news_worker.start()

    def _on_news_loaded(self, news_list):
        self.news_widget.set_news(news_list)

    def _start_client_check(self):
        """Фоновая проверка обновлений клиента при запуске."""
        self.btn_play.setEnabled(False)
        self.progress_widget.set_status("Проверка обновлений...", 0)
        self.check_worker = CheckWorker()
        self.check_worker.check_done.connect(self._on_check_done)
        self.check_worker.start()

    def _on_check_done(self, has_updates: bool):
        if has_updates:
            self._set_play_mode(False)
            if Config.has_complete_client_layout():
                self.progress_widget.set_status("Доступно обновление клиента", -1)
            else:
                self.btn_play.setText("Скачать клиент")
                self.progress_widget.set_status("Клиент не установлен", -1)
        else:
            self._set_play_mode(True)
            self.progress_widget.set_status("Готово", -1)

    def _set_play_mode(self, is_play: bool):
        """Переключить кнопку между «Играть» и «Обновить»."""
        self._play_mode = is_play
        self.btn_play.setText("Играть" if is_play else "Обновить")
        self.btn_play.setEnabled(True)

    def _on_play_clicked(self):
        if self._play_mode:
            self.play()
        else:
            self.start_update()

    def start_update(self):
        if self.worker and self.worker.isRunning():
            return
        self.progress_widget.reset()
        self.progress_widget.set_status("Проверка файлов...", 0)
        self.btn_play.setVisible(False)
        self.btn_cancel.setVisible(True)

        self.worker = UpdateWorker(Config.GAME_DIR, Config.MANIFEST_URL)
        self.worker.log_signal.connect(self._on_log_msg)
        self.worker.progress_signal.connect(self.progress_widget.set_status)
        self.worker.finished_signal.connect(self.on_update_finished)
        self.worker.start()

    def _on_log_msg(self, msg: str):
        """Обновить строку статуса из лог-сообщений воркера."""
        self.progress_widget.set_status(msg, -1)

    def cancel_update(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.progress_widget.set_status("Отмена...", -1)

    def on_update_finished(self, success: bool, message: str):
        self.progress_widget.set_status(
            message, 100 if success else 0
        )
        self.btn_play.setVisible(True)
        self.btn_cancel.setVisible(False)
        self._set_play_mode(success)
        self._refresh_info()

    def play(self):
        if not check_wow_executable():
            QMessageBox.warning(self, "Ошибка", "Wow.exe не найден в папке лаунчера!")
            return
        self.progress_widget.set_status("Запуск WoW...", -1)
        launch_wow()
        self.close()

    def open_addons(self):
        dialog = AddonsDialog(self)
        dialog.exec_()

    def open_account(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Аккаунт")
        dialog.setFixedSize(600, 300)
        dialog.setStyleSheet("""
            QDialog { background: #0f0f23; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #16213e; border: 1px solid #0f3460;
                border-radius: 7px; padding: 10px 22px; font-size: 20px;
                color: #e0e0e0;
            }
            QPushButton:hover { background: #0f3460; }
        """)

        layout = QVBoxLayout(dialog)

        msg = QLabel(
            "Управление учётной записью\n"
            "осуществляется через Telegram-бот:\n"
            "@wotlk_amatol_bot"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("font-size: 20px;")
        layout.addWidget(msg)

        btn_layout = QHBoxLayout()
        btn_open = QPushButton("Открыть бота")
        btn_open.setFixedHeight(56)
        btn_open.setStyleSheet(
            "QPushButton { background: #e94560; border: none; border-radius: 5px; "
            "font-size: 20px; font-weight: bold; color: white; }"
            "QPushButton:hover { background: #ff5570; }"
        )
        btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://t.me/wotlk_amatol_bot")))

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setFixedHeight(56)
        btn_cancel.clicked.connect(dialog.reject)

        btn_layout.addWidget(btn_open)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        dialog.exec_()

    # --- Самообновление лаунчера ---

    def _start_self_update_check(self):
        """Запустить тихую фоновую проверку обновлений лаунчера."""
        self.self_update_worker = SelfUpdateWorker()
        self.self_update_worker.update_available_signal.connect(self._on_self_update_available)
        self.self_update_worker.check_only()

    def _on_self_update_available(self, manifest: dict):
        """Обновление лаунчера доступно — показать диалог."""
        self.self_update_dialog = SelfUpdateDialog(manifest, self)

        if self.self_update_dialog.exec_() == QDialog.Accepted:
            self._start_self_update_download(manifest)

    def _start_self_update_download(self, manifest: dict):
        """Начать скачивание обновления лаунчера."""
        self.progress_widget.set_status(
            f"Скачивание лаунчера {manifest.get('version', '?')}...", -1
        )

        self.self_update_worker = SelfUpdateWorker()
        self.self_update_worker.download_progress_signal.connect(self._on_self_update_progress)
        self.self_update_worker.download_finished_signal.connect(self._on_self_update_downloaded)
        self.self_update_worker.download_and_apply(manifest)

    def _on_self_update_progress(self, downloaded: int, total: int):
        if self.self_update_dialog and self.self_update_dialog.isVisible():
            self.self_update_dialog.set_progress(downloaded, total)
        if total > 0:
            pct = int(downloaded / total * 100)
            self.progress_widget.set_status(f"Обновление лаунчера: {pct}%", pct)

    def _on_self_update_downloaded(self, success: bool, path: str):
        if not success or not path:
            self.progress_widget.set_status("Не удалось скачать обновление лаунчера.", -1)
            return

        self.progress_widget.set_status("Обновление скачано. Перезапуск...", -1)

        ok = apply_update(path)
        if ok:
            # apply_update уже запустил новый .exe и переименовал старый в .old
            QApplication.quit()
        else:
            self.progress_widget.set_status("Не удалось применить обновление.", -1)
