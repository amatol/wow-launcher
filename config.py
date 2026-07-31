"""
Конфигурация лаунчера.
Все настраиваемые параметры в одном месте.
"""
import os
import sys


class Config:
    # Папка, в которой запущен лаунчер = папка с клиентом WoW
    GAME_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

    # Исполняемый файл клиента
    WOW_EXE_NAMES = ["Dreamworld.exe", "Wow.exe", "wow.exe", "WoW.exe"]
    WOW_EXE = None

    # Версия клиента (1.12, 3.3.5a и т.д.)
    CLIENT_VERSION = "3.3.5a"

    # Файл, в котором хранится текущая версия патча клиента
    VERSION_FILE = os.path.join(GAME_DIR, ".launcher_version")

    # URL манифеста обновлений (JSON)
    MANIFEST_URL = "https://example.com/wow/manifest.json"

    # Таймаут HTTP-запросов (сек)
    HTTP_TIMEOUT = 30

    # Размер чанка при скачивании (байт)
    DOWNLOAD_CHUNK = 65536

    # Папка для временных файлов скачивания
    TEMP_DIR = os.path.join(GAME_DIR, ".launcher_tmp")

    # Пытаться ли BitTorrent, если HTTP недоступен
    TORRENT_FALLBACK = True

    # Порт для torrent-клиента
    TORRENT_PORT = 6881

    # Макс. секунд ожидания торрента перед фолбэком
    TORRENT_TIMEOUT = 300

    @classmethod
    def detect_wow_exe(cls):
        """Найти Wow.exe в папке запуска."""
        for name in cls.WOW_EXE_NAMES:
            path = os.path.join(cls.GAME_DIR, name)
            if os.path.isfile(path):
                cls.WOW_EXE = path
                return path
        return None

    @classmethod
    def get_current_version(cls):
        """Прочитать текущую версию из VERSION_FILE."""
        if os.path.isfile(cls.VERSION_FILE):
            with open(cls.VERSION_FILE, "r") as f:
                return f.read().strip()
        return None

    @classmethod
    def set_current_version(cls, version):
        """Записать текущую версию."""
        with open(cls.VERSION_FILE, "w") as f:
            f.write(version)

    @classmethod
    def ensure_temp_dir(cls):
        os.makedirs(cls.TEMP_DIR, exist_ok=True)
