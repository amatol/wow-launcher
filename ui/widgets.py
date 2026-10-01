"""
Кастомные виджеты: новости сервера и прогресс-бар.
"""
from html import escape
import requests

from PyQt5.QtWidgets import (
    QTextBrowser, QProgressBar, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
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
        self.setAccessibleName("Новости сервера")
        self.setStyleSheet(
            "QTextBrowser { background: transparent; color: #b7cedd; "
            "font-size: 14px; border: none; padding: 0; "
            "selection-background-color: #395b72; selection-color: #ffffff; }"
        )
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet(
            "a { color: #91d7ee; text-decoration: underline; }"
        )
        self._loading()

    def _loading(self):
        self.setHtml(
            "<div style='color:#9db5c6; text-align:center; padding:20px;'>"
            "Загрузка новостей..."
            "</div>"
        )

    def set_news(self, news_list: list):
        if not news_list:
            self.setHtml(
                "<div style='color:#9db5c6; text-align:center; padding:20px;'>"
                "Новости пока недоступны. Попробуйте открыть лаунчер позже."
                "</div>"
            )
            return

        html_parts = []
        for item in news_list[:5]:
            title = escape(str(item.get("title", "")))
            date = escape(str(item.get("date", "")))
            body = item.get("body", "")
            html_parts.append(
                f"<p style='color:#9db5c6; font-size:12px; margin-top:16px; margin-bottom:5px;'>{date}</p>"
                f"<p style='color:#ddba7c; font-size:17px; font-weight:bold; margin-top:0; margin-bottom:8px;'>{title}</p>"
                f"<div style='color:#b7cedd; font-size:14px;'>{body}</div>"
            )
        self.setHtml("".join(html_parts))


class ProgressWidget(QWidget):
    """Компактный виджет: подпись + прогресс-бар."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self.label = QLabel("Готово")
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setStyleSheet("color: #b7cedd; font-size: 12px;")
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.label.setWordWrap(True)
        self.label.setMaximumHeight(36)
        self.bar = QProgressBar()
        self.bar.setObjectName("downloadProgress")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedHeight(12)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName("Прогресс обновления")
        status_row = QHBoxLayout()
        status_row.addWidget(self.label, 1)
        self.percent_label = QLabel("")
        self.percent_label.setStyleSheet("color: #b7cedd; font-size: 12px;")
        status_row.addWidget(self.percent_label)
        layout.addLayout(status_row)
        layout.addWidget(self.bar)

    def set_status(self, text: str, percent: int = -1):
        self.label.setText(text)
        self.label.setToolTip(text)
        if percent >= 0:
            self.bar.setValue(percent)
            self.percent_label.setText(f"{self.bar.value()}%" if 0 < percent < 100 else "")

    def reset(self):
        self.bar.setValue(0)
        self.label.setText("Готово")
        self.label.setToolTip("")
        self.percent_label.setText("")
