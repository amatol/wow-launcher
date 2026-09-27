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

    # Публичная ссылка на базовый архив клиента. Её источником является
    # актуальная запись «Скачать клиент» в Telegram-боте.
    CLIENT_ARCHIVE_PUBLIC_URL = "https://disk.yandex.ru/d/qysMkH29wBZrIw"

    # API Яндекс Диска выдаёт временный прямой URL для публичной ссылки.
    YANDEX_DOWNLOAD_API_URL = "https://cloud-api.yandex.net/v1/disk/public/resources/download"

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

    # --- Самообновление лаунчера ---
    # Версия самого лаунчера (формат YYYYMMDD)
    LAUNCHER_VERSION = "20260927"

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
    def has_complete_client_layout(cls):
        """Базовый клиент существует, если найдены Wow.exe и каталог Data."""
        incomplete = os.path.join(cls.GAME_DIR, ".dreamworld_bootstrap_incomplete")
        return (
            not os.path.exists(incomplete)
            and cls.detect_wow_exe() is not None
            and os.path.isdir(os.path.join(cls.GAME_DIR, "Data"))
        )

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
