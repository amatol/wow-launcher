"""
Конфигурация лаунчера.
Все настраиваемые параметры в одном месте.
"""
import os
import sys


class Config:
    UPDATE_BASE_URL = "https://wotlk.amatol.blog/launcher"
    # Папка, в которой запущен лаунчер = папка с клиентом WoW
    GAME_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))

    # Исполняемый файл клиента
    WOW_EXE_NAMES = ["Wow.exe", "wow.exe", "WoW.exe"]
    WOW_EXE = None

    # Версия клиента (формат YYYYMMDD)
    CLIENT_VERSION = "20260731"

    # Файл, в котором хранится текущая версия патча клиента
    VERSION_FILE = os.path.join(GAME_DIR, ".launcher_version")

    # URL манифеста обновлений (JSON)
    MANIFEST_URL = f"{UPDATE_BASE_URL}/manifest.json"

    # URL новостей сервера (JSON: список {title, date, body})
    NEWS_URL = f"{UPDATE_BASE_URL}/news.json"

    # URL манифеста аддонов (JSON: список {name, version, url, sha256, ...})
    ADDONS_MANIFEST_URL = f"{UPDATE_BASE_URL}/addons_manifest.json"

    # Папка для аддонов внутри клиента WoW
    ADDONS_DIR = os.path.join(GAME_DIR, "Interface", "AddOns")

    # Файл с состояниями установленных аддонов
    ADDONS_STATE_FILE = os.path.join(GAME_DIR, ".launcher_addons")

    # Таймаут HTTP-запросов (сек)
    HTTP_TIMEOUT = 30

    # Размер чанка при скачивании (байт)
    DOWNLOAD_CHUNK = 65536

    # Пытаться ли BitTorrent, если HTTP недоступен
    TORRENT_FALLBACK = True

    # Порт для torrent-клиента
    TORRENT_PORT = 6881

    # Макс. секунд ожидания торрента перед фолбэком
    TORRENT_TIMEOUT = 300

    # --- Самообновление лаунчера ---
    # Версия самого лаунчера (формат YYYYMMDD)
    LAUNCHER_VERSION = "20260808"

    # URL манифеста обновлений лаунчера (JSON)
    LAUNCHER_MANIFEST_URL = f"{UPDATE_BASE_URL}/launcher_manifest.json"

    # Имя .exe файла лаунчера
    LAUNCHER_EXE_NAME = "Dreamworld.exe"

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
        import tempfile
        return tempfile.mkdtemp(prefix="dreamworld_")
