"""
Точка входа WoW Launcher.
"""
import sys
import os

# Добавить корень проекта в sys.path, чтобы импорты работали из любой точки
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from config import Config
from core.self_update import cleanup_self_update_files
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Dreamworld Launcher")

    # Иконка приложения
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "dreamworld.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Очистка мусора от прошлых обновлений
    cleanup_self_update_files()

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
