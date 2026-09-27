"""
Утилиты сетевого скачивания с ретраями.
"""
import hashlib
import os
import time
from typing import Callable, Optional, Tuple

import requests

from config import Config

ProgressCallback = Callable[[int, int, str], None]

MAX_RETRIES = 3
RETRY_DELAY = 2  # секунд между попытками


def download_with_retries(
    url: str,
    dest_path: str,
    expected_size: int = 0,
    expected_sha256: str = "",
    progress_cb: ProgressCallback = None,
    cancel_check: Callable[[], bool] = None,
    max_retries: int = MAX_RETRIES,
    session: Optional[requests.Session] = None,
) -> Tuple[bool, str]:
    """
    Скачать файл с ретраями. Возвращает (успех, сообщение_об_ошибке).

    При обрыве соединения или таймауте повторяет попытку до max_retries раз.
    Проверяет размер и SHA-256 после каждого скачивания.
    """
    last_error = ""

    for attempt in range(1, max_retries + 1):
        if cancel_check and cancel_check():
            return False, "отменено"

        resp = None
        try:
            client = session if session is not None else requests
            resp = client.get(url, stream=True, timeout=Config.HTTP_TIMEOUT)
            resp.raise_for_status()

            total = int(resp.headers.get("Content-Length", expected_size or 0))
            downloaded = 0
            h = hashlib.sha256()

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=Config.DOWNLOAD_CHUNK):
                    if cancel_check and cancel_check():
                        return False, "отменено"
                    if chunk:
                        f.write(chunk)
                        h.update(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total, f"Скачивание (попытка {attempt}/{max_retries})")

            if expected_size and downloaded != expected_size:
                last_error = f"размер не совпадает: {downloaded} вместо {expected_size}"
                if attempt < max_retries:
                    if not _retry_delay(attempt, cancel_check):
                        _remove_partial(dest_path)
                        return False, "отменено"
                    continue
                _remove_partial(dest_path)
                return False, last_error

            if expected_sha256 and h.hexdigest().lower() != expected_sha256.lower():
                last_error = f"хэш не совпадает"
                if attempt < max_retries:
                    if not _retry_delay(attempt, cancel_check):
                        _remove_partial(dest_path)
                        return False, "отменено"
                    continue
                _remove_partial(dest_path)
                return False, last_error

            return True, ""

        except requests.exceptions.ConnectionError as e:
            last_error = f"обрыв соединения: {e}"
        except requests.exceptions.Timeout:
            last_error = "таймаут соединения"
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP ошибка: {e}"
            # Для 4xx ошибок ретраи бессмысленны
            if resp.status_code >= 400 and resp.status_code < 500:
                _remove_partial(dest_path)
                return False, last_error
        except Exception as e:
            last_error = f"ошибка: {e}"

        finally:
            if resp is not None:
                resp.close()

        if attempt < max_retries:
            if progress_cb:
                progress_cb(0, 0, f"Повторная попытка {attempt + 1}/{max_retries}...")
            if not _retry_delay(attempt, cancel_check):
                _remove_partial(dest_path)
                return False, "отменено"
        else:
            if progress_cb:
                progress_cb(0, 0, f"Не удалось скачать после {max_retries} попыток")

    _remove_partial(dest_path)

    return False, last_error


def _retry_delay(attempt: int, cancel_check: Callable[[], bool] = None) -> bool:
    """Подождать 2, 4, ... секунд, сохраняя быструю реакцию на отмену."""
    deadline = time.monotonic() + RETRY_DELAY * (2 ** (attempt - 1))
    while True:
        if cancel_check and cancel_check():
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(0.1, remaining))


def _remove_partial(path: str) -> None:
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
