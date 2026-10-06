"""
Точка входа WoW Launcher.
"""
import sys
import os

# Добавить корень проекта в sys.path, чтобы импорты работали из любой точки
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QIcon

from config import Config
from core.self_update import cleanup_self_update_files, wait_for_update_parent
from ui.main_window import MainWindow


def main():
    # При самообновлении не создавать второе окно, пока старый процесс ещё завершается.
    wait_for_update_parent()

    # Эти атрибуты должны быть установлены до создания QApplication. Тогда Qt
    # использует логические пиксели и системный масштаб каждого монитора.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Dreamworld Launcher")
    app.setOrganizationName("Dreamworld")
    app.setOrganizationDomain("wotlk.amatol.blog")

    if "--smoke-test" in sys.argv:
        # Проверка упакованного Qt и встроенного Wine без подключения к серверу.
        from config import app_bundle_path
        import subprocess
        bundle = app_bundle_path()
        if bundle and sys.platform == "darwin":
            resources = os.path.join(bundle, "Contents", "Resources")
            assert Config.GAME_DIR == os.path.dirname(bundle)
            from pathlib import Path
            from core.macos_setup import wine_environment
            env = wine_environment(Path(resources), Config.GAME_DIR)
            subprocess.run([os.path.join(resources, "Wine", "bin", "wine"), "--version"],
                           env=env, check=True, timeout=30)
        print("Dreamworld smoke test OK", Config.LAUNCHER_VERSION, flush=True)
        return

    # Иконка приложения
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "dreamworld.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Очистка мусора от прошлых обновлений
    cleanup_self_update_files()

    if sys.platform == "darwin" and Config.detect_wow_exe():
        from core.macos_setup import prepare_game_config
        try:
            prepare_game_config(Config.GAME_DIR)
        except Exception as error:
            QMessageBox.warning(None, "Настройки WoW", f"Не удалось подготовить настройки игры: {error}")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
