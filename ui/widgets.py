"""
Кастомные виджеты: новости сервера и прогресс-бар.
"""
import requests

from PyQt5.QtWidgets import (
    QTextBrowser, QProgressBar, QWidget, QVBoxLayout, QLabel
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread

from config import Config


class NewsWorker(QThread):
    """Фоновый поток загрузки новостей."""

    news_signal = pyqtSignal(list)  # список dict: title, date, body

    def run(self):
        try:
            resp = requests.get(Config.NEWS_URL, timeout=Config.HTTP_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                self.news_signal.emit(data)
            elif isinstance(data, dict) and "news" in data:
                self.news_signal.emit(data["news"])
        except Exception:
            self.news_signal.emit([])


class NewsWidget(QTextBrowser):
    """Виджет отображения новостей сервера."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setStyleSheet(
            "QTextBrowser { background: #1a1a2e; color: #c0c0c0; "
            "font-family: 'Segoe UI', sans-serif; font-size: 20px; "
            "border: 1px solid #0f3460; border-radius: 10px; padding: 14px; }"
        )
        self._loading()

    def _loading(self):
        self.setHtml(
            "<div style='color:#666; text-align:center; padding:20px;'>"
            "Загрузка новостей..."
            "</div>"
        )

    def set_news(self, news_list: list):
        if not news_list:
            self.setHtml(
                "<div style='color:#666; text-align:center; padding:20px;'>"
                "Новостей пока нет."
                "</div>"
            )
            return

        html_parts = []
        for item in news_list:
            title = item.get("title", "")
            date = item.get("date", "")
            body = item.get("body", "")
            html_parts.append(
                f"<div style='margin-bottom:16px;'>"
                f"<div style='color:#e94560; font-size:24px; font-weight:bold;'>{title}</div>"
                f"<div style='color:#888; font-size:17px; margin-bottom:10px;'>{date}</div>"
                f"<div style='color:#c0c0c0;'>{body}</div>"
                f"</div>"
            )
        self.setHtml("".join(html_parts))


class ProgressWidget(QWidget):
    """Компактный виджет: подпись + прогресс-бар."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = QLabel("Готово")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #a0a0a0; font-size: 18px;")

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedHeight(30)
        self.bar.setStyleSheet(
            "QProgressBar { background: #16213e; border: 1px solid #0f3460; "
            "border-radius: 6px; text-align: center; color: white; font-size: 17px; }"
            "QProgressBar::chunk { background: #e94560; border-radius: 3px; }"
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
