"""
Кастомные виджеты: лог-консоль и круговой/линейный прогресс.
"""
from PyQt5.QtWidgets import (
    QPlainTextEdit, QProgressBar, QWidget, QVBoxLayout, QLabel
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QTextCursor


class LogWidget(QPlainTextEdit):
    """Текстовая консоль для вывода лога."""

    append_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setStyleSheet(
            "QPlainTextEdit { background: #1a1a2e; color: #c0c0c0; "
            "font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; }"
        )
        self.append_signal.connect(self._append)

    def log(self, msg: str):
        self.append_signal.emit(msg)

    def _append(self, msg: str):
        self.appendPlainText(msg)
        self.moveCursor(QTextCursor.End)


class ProgressWidget(QWidget):
    """Виджет с подписью + прогресс-бар + проценты."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel("Готово")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #e0e0e0; font-size: 13px;")

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setStyleSheet(
            "QProgressBar { background: #16213e; border: 1px solid #0f3460; "
            "border-radius: 4px; text-align: center; color: white; }"
            "QProgressBar::chunk { background: #0f3460; border-radius: 3px; }"
        )
        self.bar.setTextVisible(True)

        layout.addWidget(self.label)
        layout.addWidget(self.bar)

    def set_status(self, text: str, percent: int = -1):
        self.label.setText(text)
        if percent >= 0:
            self.bar.setValue(percent)

    def reset(self):
        self.bar.setValue(0)
        self.label.setText("Готово")
