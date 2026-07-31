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
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Dreamworld Launcher")

    # Иконка приложения
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "dreamworld.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Убедимся, что папка-конфиг существует
    Config.ensure_temp_dir()

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
