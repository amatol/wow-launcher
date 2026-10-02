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
from PyQt5.QtGui import QDesktopServices

from config import Config
from core.version import check_wow_executable, launch_wow, get_current_version, set_current_version
from core.self_update import (
    fetch_launcher_manifest, is_update_available,
    download_update, apply_update,
)
from updater.manifest import (
    Manifest, compute_existing_removed_files, filter_needed,
)
from updater.http_updater import HTTPUpdater
from updater.bootstrap import BootstrapInstaller
from ui.widgets import NewsWidget, NewsWorker, ProgressWidget
from ui.addons_dialog import AddonsDialog
from ui.theme import STYLESHEET, LandscapeWidget, load_display_font


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
            from core.launcher_bundle import companion_needed
            self.check_done.emit(bool(needed or removed or companion_needed(manifest.raw, Config.GAME_DIR)))
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
        self.installed_base_client = False

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
                self.installed_base_client = True
                self.log_signal.emit(message)

            self.log_signal.emit("Проверка файлов клиента...")
            manifest = Manifest.fetch(self.manifest_url)
            self.log_signal.emit(f"Манифест: версия {manifest.version}, файлов: {len(manifest.files)}")

            needed = filter_needed(manifest, Config.get_current_version(), self.game_dir)
            removed = compute_existing_removed_files(manifest, self.game_dir)

            from core.launcher_bundle import sync_companion

            if not needed and not removed:
                sync_companion(manifest.raw, self.game_dir)
                set_current_version(manifest.version)
                self.finished_signal.emit(True, "Клиент актуален. Обновлений нет.")
                return

            self.log_signal.emit(
                f"Нужно обновить: {len(needed)} из {len(manifest.files)} файлов; "
                f"удалить устаревших: {len(removed)}"
            )

            # Скачивание обновлений по HTTP
            self.log_signal.emit("HTTP-обновление...")
            self._updater = HTTPUpdater(self.game_dir, manifest, self._progress_cb)
            ok, count = self._updater.apply_all(needed)

            if ok:
                if self._cancel:
                    self.finished_signal.emit(False, "Обновление отменено.")
                    return
                sync_companion(manifest.raw, self.game_dir)
                set_current_version(manifest.version)
                self.finished_signal.emit(
                    True, f"Обновление завершено. Обновлено файлов: {count}, удалено: {len(removed)}"
                )
                return

            if self._cancel:
                self.finished_signal.emit(False, "Обновление отменено.")
                return

            self.finished_signal.emit(
                False,
                f"Не удалось скачать все обновления. Обновлено файлов: {count} из {len(needed)}. "
                "Проверьте подключение к интернету и повторите попытку.",
            )

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
        self.resize(540, 320)
        self.setMinimumSize(480, 260)
        self._apply_theme()

        layout = QVBoxLayout(self)

        remote_ver = manifest.get("version", "?")
        changelog = manifest.get("changelog", "")

        label = QLabel(
            f"Доступна новая версия лаунчера: {remote_ver}\n"
            f"Текущая версия: {Config.LAUNCHER_VERSION}"
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #e4edf2; font-size: 16px;")
        layout.addWidget(label)

        if changelog:
            ch_label = QLabel(f"Что нового:\n{changelog}")
            ch_label.setStyleSheet("color: #b7cedd; font-size: 14px;")
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
        self.btn_yes.setFixedHeight(42)
        self.btn_no.setFixedHeight(42)
        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        layout.addLayout(btn_layout)

        self.btn_yes.setProperty("role", "primary")
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no.clicked.connect(self.reject)

    def _apply_theme(self):
        self.setStyleSheet(STYLESHEET)

    def set_progress(self, downloaded: int, total: int):
        self.progress_bar.setVisible(True)
        if total > 0:
            self.progress_bar.setValue(int(downloaded / total * 100))


class MainWindow(QMainWindow):
    DEFAULT_WIDTH = 1000
    DEFAULT_HEIGHT = 560
    MINIMUM_WIDTH = 720
    MINIMUM_HEIGHT = 400
    # A new key applies the smaller default once without disabling future restores.
    SETTINGS_GEOMETRY_KEY = "main_window/geometry_compact_v2"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wrath of the Lich King AI Launcher")
        self.setMinimumSize(self.MINIMUM_WIDTH, self.MINIMUM_HEIGHT)
        self.worker = None
        self.self_update_worker = None
        self.self_update_dialog = None
        self.news_worker = None
        self.check_worker = None

        self._apply_dark_theme()

        load_display_font()
        central = LandscapeWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(14)

        # Заголовок остаётся текстом: чёткий при системном масштабировании.
        self.title = QLabel("Wrath of the Lich King AI")
        self.title.setObjectName("gameTitle")
        self.title.setStyleSheet(
            "font-family: 'Cinzel'; font-size: 30px; color: #e4edf2;"
        )
        self.title.setAccessibleName("Wrath of the Lich King AI")
        outer.addWidget(self.title)

        self.subtitle = subtitle = QLabel("Мир Азерота. Ваше приключение.")
        subtitle.setStyleSheet("color: #b7cedd; font-size: 14px;")
        outer.addWidget(subtitle)

        main_row = QHBoxLayout()
        main_row.setSpacing(28)
        news_panel = QFrame()
        news_panel.setObjectName("newsPanel")
        news_panel.setStyleSheet(
            "QFrame#newsPanel { background: rgba(9, 21, 33, 220); "
            "border: 1px solid #304657; border-radius: 6px; }"
        )
        news_layout = QVBoxLayout(news_panel)
        news_layout.setContentsMargins(18, 14, 12, 10)
        news_layout.setSpacing(8)
        news_title = QLabel("Новости мира")
        news_title.setStyleSheet("color: #e4edf2; font-size: 17px; font-weight: bold;")
        news_layout.addWidget(news_title)
        self.news_widget = NewsWidget()
        news_layout.addWidget(self.news_widget, 1)
        main_row.addWidget(news_panel, 1)

        right_panel = QWidget()
        right_panel.setFixedWidth(230)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right_layout.addStretch(1)
        self.client_label = QLabel()
        self.client_label.setWordWrap(True)
        self.client_label.setStyleSheet("color: #b7cedd; font-size: 13px;")
        right_layout.addWidget(self.client_label)

        self.btn_play = QPushButton("Играть")
        self.btn_play.setProperty("role", "primary")
        self.btn_play.setFixedHeight(56)
        self._play_mode = True
        self.btn_play.clicked.connect(self._on_play_clicked)
        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setProperty("role", "cancel")
        self.btn_cancel.setFixedHeight(56)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.cancel_update)
        right_layout.addWidget(self.btn_play)
        right_layout.addWidget(self.btn_cancel)
        self.btn_addons = QPushButton("Аддоны")
        self.btn_addons.setFixedHeight(40)
        self.btn_addons.clicked.connect(self.open_addons)
        self.btn_account = QPushButton("Аккаунт")
        self.btn_account.setFixedHeight(40)
        self.btn_account.clicked.connect(self.open_account)
        right_layout.addWidget(self.btn_addons)
        right_layout.addWidget(self.btn_account)
        for button in (self.btn_play, self.btn_cancel, self.btn_addons, self.btn_account):
            button.setCursor(Qt.PointingHandCursor)
        main_row.addWidget(right_panel)
        outer.addLayout(main_row, 1)

        self.progress_widget = ProgressWidget()
        outer.addWidget(self.progress_widget)
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #9db5c6; font-size: 11px;")
        outer.addWidget(self.info_label)

        self._restore_window_geometry()

        self._refresh_info()
        self._load_news()
        self._start_client_check()

        # Фоновая проверка обновлений лаунчера (тихая)
        self._start_self_update_check()

    def _apply_dark_theme(self):
        self.setStyleSheet(STYLESHEET)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "title"):
            return
        compact = self.width() < 850 or self.height() < 500
        self.title.setText("Wrath of the Lich King AI")
        self.title.setStyleSheet(
            "font-family: 'Cinzel'; color: #e4edf2; font-size: "
            + ("22px;" if compact else "30px;")
        )
        self.subtitle.setVisible(not compact)
        self.centralWidget().layout().setContentsMargins(
            *((18, 16, 18, 18) if compact else (28, 24, 28, 24))
        )
        self.centralWidget().layout().setSpacing(8 if compact else 14)

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
        client_installed = Config.has_complete_client_layout()
        client_version = get_current_version()
        self.client_label.setText("Клиент установлен" if client_installed else "Начните с установки клиента")
        self.info_label.setText(
            f"Лаунчер {Config.LAUNCHER_VERSION}    /    Клиент {client_version or 'не установлен'}"
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
        self.btn_cancel.setVisible(False)
        if success and self.worker and self.worker.installed_base_client:
            # Do not expose Play between bootstrap extraction and a fresh
            # check of the files now present on disk.  If that check finds
            # anything, immediately run the normal updater in this launch.
            self.progress_widget.set_status("Проверка обновлений установленного клиента...", 0)
            self.post_bootstrap_check_worker = CheckWorker()
            self.post_bootstrap_check_worker.check_done.connect(
                self._on_post_bootstrap_check_done
            )
            self.post_bootstrap_check_worker.start()
            self._refresh_info()
            return

        self.btn_play.setVisible(True)
        self._set_play_mode(success)
        self._refresh_info()

    def _on_post_bootstrap_check_done(self, has_updates: bool):
        if has_updates:
            self.worker = None
            self.start_update()
            return
        self.btn_play.setVisible(True)
        self._set_play_mode(True)
        self.progress_widget.set_status("Клиент актуален. Обновлений нет.", 100)
        self._refresh_info()

    def play(self):
        if not check_wow_executable():
            QMessageBox.warning(self, "Ошибка", "Wow.exe не найден в папке лаунчера!")
            return
        self.progress_widget.set_status("Запуск WoW...", -1)
        try:
            if not launch_wow():
                raise RuntimeError("Не удалось запустить Wow.exe")
        except Exception as error:
            QMessageBox.warning(self, "Ошибка запуска", str(error))
            self.progress_widget.set_status("Не удалось запустить WoW.", -1)
            return
        self.close()

    def open_addons(self):
        dialog = AddonsDialog(self)
        dialog.exec_()

    def open_account(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Аккаунт")
        dialog.setFixedSize(470, 240)
        dialog.setStyleSheet(STYLESHEET)

        layout = QVBoxLayout(dialog)

        msg = QLabel(
            "Управление учётной записью\n"
            "осуществляется через Telegram-бот:\n"
            "@wotlk_amatol_bot"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("font-size: 16px;")
        layout.addWidget(msg)

        btn_layout = QHBoxLayout()
        btn_open = QPushButton("Открыть бота")
        btn_open.setFixedHeight(44)
        btn_open.setProperty("role", "primary")
        btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://t.me/wotlk_amatol_bot")))

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setFixedHeight(44)
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
