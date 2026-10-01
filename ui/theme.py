"""Общая палитра и ресурсы интерфейса Нордскола."""
from pathlib import Path

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QFontDatabase, QLinearGradient, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget


ASSETS = Path(__file__).resolve().parent.parent / "assets"
_font_loaded = False


def load_display_font():
    global _font_loaded
    if not _font_loaded:
        QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / "Cinzel.ttf"))
        _font_loaded = True


STYLESHEET = """
QMainWindow, QDialog { background: #091521; }
QWidget { color: #e4edf2; font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 14px; }
QLabel { background: transparent; }
QPushButton {
    background: #142b3b; color: #dce9f0; border: 1px solid #395263;
    border-radius: 5px; padding: 8px 16px; font-size: 14px;
}
QPushButton:hover { background: #203d50; border-color: #76bfd5; }
QPushButton:pressed { background: #0c1e2c; }
QPushButton:focus { border: 2px solid #b9e8f7; }
QPushButton:disabled { background: #15232e; color: #8197a5; border-color: #304350; }
QPushButton[role="primary"] {
    background: #ddba7c; color: #18212a; border: 1px solid #f0d4a5;
    font-weight: bold; font-size: 18px;
}
QPushButton[role="primary"]:hover { background: #f0d4a5; }
QPushButton[role="primary"]:pressed { background: #c6a067; }
QPushButton[role="primary"]:focus { border: 2px solid #ffffff; }
QPushButton[role="primary"]:disabled { background: #38434a; color: #acbdc8; border-color: #52616a; }
QPushButton[role="cancel"] { color: #f2c0b5; border-color: #95695f; }
QPushButton[role="cancel"]:hover { background: #49302e; }
QProgressBar {
    background: #102331; border: 1px solid #395263; border-radius: 4px;
    text-align: center; color: #e4edf2; min-height: 8px;
}
QProgressBar::chunk { background: #315c70; border-radius: 3px; }
QProgressBar#downloadProgress { min-height: 0px; padding: 0px; }
QProgressBar#downloadProgress::chunk { background: #76bfd5; }
QScrollBar:vertical { background: #102331; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #456378; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #76bfd5; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollArea { background: transparent; border: none; }
QCheckBox { color: #e4edf2; spacing: 10px; }
QCheckBox:focus { outline: 1px solid #b9e8f7; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #7995a8; border-radius: 3px; background: #142b3b; }
QCheckBox::indicator:hover { border-color: #b9e8f7; }
QCheckBox::indicator:checked { background: #ddba7c; border-color: #f0d4a5; image: url("CHECK_ASSET"); }
QCheckBox::indicator:disabled { border-color: #395263; background: #304350; }
QToolTip { background: #142b3b; color: #e4edf2; border: 1px solid #76bfd5; padding: 6px; }
"""
STYLESHEET = STYLESHEET.replace("CHECK_ASSET", (ASSETS / "check.svg").as_posix())


class LandscapeWidget(QWidget):
    """Иллюстрация рисуется один раз на размер окна, без анимации и таймеров."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap(str(ASSETS / "northrend.png"))
        self._scaled = QPixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._source.isNull():
            self._scaled = self._source.scaled(
                self.size() * self.devicePixelRatioF(), Qt.KeepAspectRatioByExpanding,
                Qt.FastTransformation,
            )
            self._scaled.setDevicePixelRatio(self.devicePixelRatioF())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#091521"))
        if not self._scaled.isNull():
            # Верхний край сохраняет силуэт цитадели при любом соотношении сторон.
            width = self._scaled.width() / self._scaled.devicePixelRatioF()
            painter.drawPixmap(int(self.width() - width), 0, self._scaled)
        veil = QLinearGradient(0, 0, self.width(), 0)
        veil.setColorAt(0, QColor(9, 21, 33, 185))
        veil.setColorAt(0.6, QColor(9, 21, 33, 65))
        veil.setColorAt(1, QColor(9, 21, 33, 15))
        painter.fillRect(self.rect(), veil)
        floor = QLinearGradient(0, self.height() * 0.45, 0, self.height())
        floor.setColorAt(0, QColor(9, 21, 33, 0))
        floor.setColorAt(1, QColor(9, 21, 33, 250))
        painter.fillRect(QRect(0, 0, self.width(), self.height()), floor)
