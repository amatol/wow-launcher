"""
Диалог управления аддонами.
Показывает список аддонов с чекбоксами, версиями и описаниями.
Позволяет выбрать и установить/обновить аддоны.
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QCheckBox, QProgressBar, QMessageBox,
    QFrame, QGridLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from ui.theme import STYLESHEET
from updater.addons import (
    fetch_addons_manifest, AddonEntry, inspect_addon,
    install_selected,
)


class AddonsFetchWorker(QThread):
    """Фоновая загрузка манифеста аддонов."""

    fetched = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, parent=None, addons=None):
        super().__init__(parent)
        self._addons = addons

    def run(self):
        try:
            addons = self._addons if self._addons is not None else fetch_addons_manifest()
            if addons is None:
                raise ValueError("Не удалось загрузить список аддонов. Проверьте соединение и повторите.")
            for entry in addons:
                if self.isInterruptionRequested():
                    return
                inspect_addon(entry)
            self.fetched.emit(addons)
        except Exception as error:
            self.failed.emit(f"Не удалось проверить аддоны: {error}")


class AddonsInstallWorker(QThread):
    """Фоновая установка выбранных аддонов."""

    progress_signal = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(bool, int, str)

    def __init__(self, addons: list):
        super().__init__()
        self._addons = addons

    def run(self):
        try:
            ok, count, errors = install_selected(
                self._addons,
                lambda i, total, msg: self.progress_signal.emit(i, total, msg),
            )
            self.finished_signal.emit(ok, count, "\n".join(errors))
        except Exception as error:
            self.finished_signal.emit(False, 0, str(error))


class AddonRow(QFrame):
    """Строка аддона: чекбокс + имя + версии + описание."""

    def __init__(self, entry: AddonEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            "QFrame { background: #102331; border-radius: 6px; margin-bottom: 4px; }"
        )

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.checkbox = QCheckBox()
        self.checkbox.setStyleSheet("QCheckBox { color: #e4edf2; font-size: 16px; font-weight: bold; }")
        self.checkbox.setText(entry.name)
        layout.addWidget(self.checkbox, 0, 0)

        remote_ver_label = QLabel(f"Сервер: {entry.version}")
        remote_ver_label.setStyleSheet("color: #b7cedd; font-size: 14px;")
        layout.addWidget(remote_ver_label, 1, 0)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #b7cedd; font-size: 14px;")
        layout.addWidget(self.status_label, 2, 0)
        self.update_label = QLabel("Доступно обновление")
        self.update_label.setStyleSheet("color: #ddba7c; font-size: 14px;")
        layout.addWidget(self.update_label, 1, 1)

        if entry.description:
            desc_label = QLabel(entry.description)
            desc_label.setStyleSheet("color: #b7cedd; font-size: 14px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label, 3, 0, 1, 2)

        self.refresh_status()
        self.checkbox.setChecked(entry.installed)

    def refresh_status(self):
        entry = self.entry
        if not entry.installed:
            text = "Не установлен"
        elif entry.installed_version:
            text = f"Установлено: {entry.installed_version}"
        else:
            text = "Установлен; файлы отличаются от текущего выпуска"
        self.status_label.setText(text)
        self.status_label.setWordWrap(True)
        self.update_label.setVisible(entry.update_available)


class AddonsDialog(QDialog):
    """Диалог управления аддонами."""

    addons_changed = pyqtSignal(list)

    def __init__(self, parent=None, auto_update=False):
        super().__init__(parent)
        self._auto_update = auto_update
        self._busy = False
        self._scan_valid = False
        self.setWindowTitle("Аддоны")
        self.resize(720, 600)
        self.setMinimumSize(680, 480)
        self._apply_theme()

        self.addons = []
        self.rows = []
        self.install_worker = None
        self.fetch_worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        # Заголовок
        title = QLabel("Управление аддонами")
        title.setStyleSheet("color: #ddba7c; font-size: 19px; font-weight: bold;")
        layout.addWidget(title)

        # Зона прокрутки со списком аддонов
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("addonList")
        self.scroll_content.setStyleSheet("QWidget#addonList { background: #091521; }")
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
        self.progress_bar.setFixedHeight(24)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Загрузка списка аддонов...")
        self.status_label.setStyleSheet("color: #b7cedd; font-size: 14px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Кнопки
        btn_layout = QHBoxLayout()

        self.btn_select_all = QPushButton("Выбрать все")
        self.btn_select_all.setFixedHeight(42)
        self.btn_select_all.clicked.connect(self._select_all)

        self.btn_deselect_all = QPushButton("Снять выделение")
        self.btn_deselect_all.setFixedHeight(42)
        self.btn_deselect_all.clicked.connect(self._deselect_all)

        self.btn_install = QPushButton("Установить")
        self.btn_install.setFixedHeight(42)
        self.btn_install.setProperty("role", "primary")
        self.btn_install.setStyleSheet("font-size: 14px;")
        self.btn_install.clicked.connect(self._on_install)

        self.btn_retry = QPushButton("Повторить")
        self.btn_retry.setFixedHeight(42)
        self.btn_retry.clicked.connect(self._load_addons)
        self.btn_retry.hide()

        self.btn_close = QPushButton("Закрыть")
        self.btn_close.setFixedHeight(42)
        self.btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addWidget(self.btn_deselect_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_retry)
        btn_layout.addWidget(self.btn_install)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

        self._load_addons()

    def _apply_theme(self):
        self.setStyleSheet(STYLESHEET)

    def _load_addons(self):
        self._scan_addons()

    def _set_busy(self, busy):
        self._busy = busy
        for button in (self.btn_install, self.btn_select_all, self.btn_deselect_all, self.btn_retry):
            button.setEnabled(not busy)
        self.btn_close.setEnabled(not busy)
        for row in self.rows:
            row.checkbox.setEnabled(not busy)

    def _scan_addons(self, addons=None):
        self._scan_valid = False
        self._set_busy(True)
        self.btn_retry.hide()
        self.status_label.setText("Проверка установленных аддонов...")
        self.fetch_worker = AddonsFetchWorker(self, addons=addons)
        self.fetch_worker.fetched.connect(self._on_addons_fetched)
        self.fetch_worker.failed.connect(self._on_fetch_failed)
        self.fetch_worker.start()

    def _on_fetch_failed(self, message):
        self._set_busy(False)
        self.btn_install.setEnabled(False)
        self.btn_retry.show()
        self.status_label.setText(message)

    def reject(self):
        if not self._busy:
            super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
        else:
            super().closeEvent(event)

    def _on_addons_fetched(self, addons: list):
        previous_selection = {row.entry.name: row.checkbox.isChecked() for row in self.rows}
        self.addons = addons
        self._scan_valid = True
        self._set_busy(False)

        # Перестроить строки с актуальными статусами.
        while self.scroll_layout.count() > 0:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.rows = []
        for entry in addons:
            row = AddonRow(entry)
            if entry.name in previous_selection:
                row.checkbox.setChecked(previous_selection[entry.name])
            row.checkbox.toggled.connect(self._refresh_action)
            self.rows.append(row)
            self.scroll_layout.addWidget(row)

        self.scroll_layout.addStretch()
        updates = sum(entry.update_available for entry in addons)
        self.status_label.setText(
            f"Установлено: {sum(entry.installed for entry in addons)} · Обновлений: {updates}"
            if addons else "В каталоге пока нет аддонов."
        )
        self._refresh_action()
        self.addons_changed.emit(addons)
        if self._auto_update:
            self._auto_update = False
            self._install([entry for entry in addons if entry.update_available])

    def _refresh_action(self):
        pending = self._get_selected()
        has_new = any(not entry.installed for entry in pending)
        has_updates = any(entry.update_available for entry in pending)
        self.btn_install.setText(
            "Установить и обновить" if has_new and has_updates else
            "Обновить" if has_updates else "Установить"
        )
        self.btn_install.setEnabled(bool(pending) and not self._busy and self._scan_valid)

    def _select_all(self):
        for row in self.rows:
            row.checkbox.setChecked(True)

    def _deselect_all(self):
        for row in self.rows:
            row.checkbox.setChecked(False)

    def _get_selected(self) -> list:
        return [row.entry for row in self.rows if row.checkbox.isChecked()
                and (not row.entry.installed or row.entry.update_available)]

    def _on_install(self):
        self._install(self._get_selected())

    def _install(self, selected):
        if not selected or self._busy or not self._scan_valid:
            return
        self._set_busy(True)
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

    def _on_install_finished(self, success: bool, count: int, error: str):
        self.progress_bar.setVisible(False)
        if success:
            self.status_label.setText(f"Установлено аддонов: {count}")
        else:
            details = error or "Причина не определена"
            self.status_label.setText(f"Установлено {count} из выбранных")
            QMessageBox.warning(self, "Ошибка установки аддонов", details)

        # После частичного сбоя также сверяем файлы, сохраняя выбор игрока.
        self._scan_addons(self.addons)
