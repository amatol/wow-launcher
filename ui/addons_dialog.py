"""
Диалог управления аддонами.
Показывает список аддонов с чекбоксами, версиями и описаниями.
Позволяет выбрать и установить/обновить аддоны.
"""
import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QCheckBox, QProgressBar, QMessageBox,
    QFrame, QGridLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from config import Config
from updater.addons import (
    fetch_addons_manifest, AddonEntry, needs_update, get_installed_version,
    install_selected,
)


class AddonsFetchWorker(QThread):
    """Фоновая загрузка манифеста аддонов."""

    fetched = pyqtSignal(list)  # список AddonEntry

    def run(self):
        addons = fetch_addons_manifest()
        self.fetched.emit(addons or [])


class AddonsInstallWorker(QThread):
    """Фоновая установка выбранных аддонов."""

    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(bool, int)

    def __init__(self, addons: list):
        super().__init__()
        self._addons = addons

    def run(self):
        ok, count = install_selected(
            self._addons,
            lambda i, total, msg: self.progress_signal.emit(i, total, msg),
        )
        self.finished_signal.emit(ok, count)


class AddonRow(QFrame):
    """Строка аддона: чекбокс + имя + версии + описание."""

    def __init__(self, entry: AddonEntry, installed_version: str = None, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            "QFrame { background: #16213e; border-radius: 6px; margin-bottom: 4px; }"
        )

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.checkbox = QCheckBox()
        self.checkbox.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 14px; font-weight: bold; }")
        self.checkbox.setText(entry.name)
        layout.addWidget(self.checkbox, 0, 0)

        remote_ver_label = QLabel(f"Сервер: {entry.version}")
        remote_ver_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(remote_ver_label, 1, 0)

        if installed_version:
            status_label = QLabel(f"Установлено: {installed_version}")
            if installed_version != entry.version:
                status_label.setStyleSheet("color: #e94560; font-size: 11px;")
                update_label = QLabel("● Доступно обновление")
                update_label.setStyleSheet("color: #e94560; font-size: 11px;")
                layout.addWidget(update_label, 1, 1)
            else:
                status_label.setStyleSheet("color: #5cb85c; font-size: 11px;")
            layout.addWidget(status_label, 2, 0)
        else:
            not_installed = QLabel("Не установлен")
            not_installed.setStyleSheet("color: #a0a0a0; font-size: 11px;")
            layout.addWidget(not_installed, 2, 0)

        if entry.description:
            desc_label = QLabel(entry.description)
            desc_label.setStyleSheet("color: #888; font-size: 11px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label, 3, 0, 1, 2)

        # По умолчанию отмечен если не установлен или есть обновление
        if not installed_version or (installed_version and installed_version != entry.version):
            self.checkbox.setChecked(True)


class AddonsDialog(QDialog):
    """Диалог управления аддонами."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Аддоны")
        self.setFixedSize(520, 520)
        self._apply_theme()

        self.addons = []
        self.rows = []
        self.install_worker = None
        self.fetch_worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Заголовок
        title = QLabel("Управление аддонами")
        title.setStyleSheet("color: #e94560; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Зона прокрутки со списком аддонов
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea { background: #0f0f23; border: none; }"
            "QScrollBar:vertical { background: #16213e; width: 8px; }"
            "QScrollBar::handle:vertical { background: #0f3460; border-radius: 4px; }"
        )
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(2)
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll, stretch=1)

        # Прогресс
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #16213e; border: 1px solid #0f3460; "
            "border-radius: 4px; text-align: center; color: white; font-size: 11px; }"
            "QProgressBar::chunk { background: #e94560; border-radius: 3px; }"
        )
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Загрузка списка аддонов...")
        self.status_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Кнопки
        btn_layout = QHBoxLayout()

        self.btn_select_all = QPushButton("Выбрать все")
        self.btn_select_all.setFixedHeight(36)
        self.btn_select_all.clicked.connect(self._select_all)

        self.btn_deselect_all = QPushButton("Снять выделение")
        self.btn_deselect_all.setFixedHeight(36)
        self.btn_deselect_all.clicked.connect(self._deselect_all)

        self.btn_install = QPushButton("Установить")
        self.btn_install.setFixedHeight(36)
        self.btn_install.setStyleSheet(
            "QPushButton { background: #e94560; border: none; border-radius: 5px; "
            "font-size: 13px; font-weight: bold; color: white; }"
            "QPushButton:hover { background: #ff5570; }"
        )
        self.btn_install.clicked.connect(self._on_install)

        self.btn_close = QPushButton("Закрыть")
        self.btn_close.setFixedHeight(36)
        self.btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_install)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self._load_addons()

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog { background: #0f0f23; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #16213e; border: 1px solid #0f3460;
                border-radius: 5px; padding: 6px 16px; font-size: 13px;
                color: #e0e0e0;
            }
            QPushButton:hover { background: #0f3460; }
            QCheckBox { color: #e0e0e0; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 2px solid #0f3460; border-radius: 3px;
                background: #1a1a2e;
            }
            QCheckBox::indicator:checked {
                background: #e94560; border-color: #e94560;
            }
        """)

    def _load_addons(self):
        self.fetch_worker = AddonsFetchWorker()
        self.fetch_worker.fetched.connect(self._on_addons_fetched)
        self.fetch_worker.start()

    def _on_addons_fetched(self, addons: list):
        self.addons = addons

        # Очистить placeholder
        while self.scroll_layout.count() > 0:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not addons:
            self.status_label.setText("Аддонов не найдено или сервер недоступен.")
            self.btn_install.setEnabled(False)
            return

        for entry in addons:
            row = AddonRow(entry, get_installed_version(entry.name))
            self.rows.append(row)
            self.scroll_layout.addWidget(row)

        self.scroll_layout.addStretch()
        self.status_label.setText(f"Доступно аддонов: {len(addons)}")
        self.btn_install.setEnabled(True)

    def _select_all(self):
        for row in self.rows:
            row.checkbox.setChecked(True)

    def _deselect_all(self):
        for row in self.rows:
            row.checkbox.setChecked(False)

    def _get_selected(self) -> list:
        return [row.entry for row in self.rows if row.checkbox.isChecked()]

    def _on_install(self):
        selected = self._get_selected()
        if not selected:
            QMessageBox.information(self, "Аддоны", "Выберите хотя бы один аддон.")
            return

        self.btn_install.setEnabled(False)
        self.btn_select_all.setEnabled(False)
        self.btn_deselect_all.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Установка аддонов...")

        self.install_worker = AddonsInstallWorker(selected)
        self.install_worker.progress_signal.connect(self._on_install_progress)
        self.install_worker.finished_signal.connect(self._on_install_finished)
        self.install_worker.start()

    def _on_install_progress(self, current: int, total: int, msg: str):
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_install_finished(self, success: bool, count: int):
        self.progress_bar.setVisible(False)
        self.btn_install.setEnabled(True)
        self.btn_select_all.setEnabled(True)
        self.btn_deselect_all.setEnabled(True)
        if success:
            self.status_label.setText(f"Установлено аддонов: {count}")
        else:
            self.status_label.setText(f"Установлено {count} из выбранных (были ошибки)")

        # Обновить статусы строк
        for row in self.rows:
            ver = get_installed_version(row.entry.name)
            if ver == row.entry.version:
                row.checkbox.setChecked(False)
