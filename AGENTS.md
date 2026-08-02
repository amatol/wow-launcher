# AGENTS.md — Dreamworld Launcher

**Python 3.10+ / PyQt5 / Windows GUI app.** Кросс-сборка .exe через GitHub Actions (windows-latest). Локальная разработка на macOS через venv.

## Восстановление контекста при каждом запуске

Перед любой работой в `/root/launcher` обязательно:

1. Полностью прочитать этот файл и `PROJECT_STATE.md`.
2. Проверить `git status --short --branch` и `git log --oneline -10`.
3. Изучить относящиеся к задаче код, конфигурацию и документацию.
4. После существенного этапа обновить `PROJECT_STATE.md`, не записывая туда
   пароли, токены, приватные ключи и персональные данные.

Не считать сведения из диалога единственным источником состояния: устойчивые
решения, выполненные инфраструктурные действия, проверки и ближайшие шаги
должны оставаться в репозитории.

## Git и фиксация изменений

- После завершения логически цельного и проверенного изменения самостоятельно
  создать содержательный Git-коммит, не запрашивая отдельного подтверждения.
- Если изменение должно попасть в рабочий репозиторий или запустить штатный
  CI/release-процесс, самостоятельно выполнить push после успешных проверок.
- Перед коммитом проверить diff и добавить только файлы текущей задачи.
- Не включать секреты, файлы клиента WoW, логи, временные файлы и сборочные
  артефакты.
- Не создавать коммит, если значимая проверка не прошла или изменения нельзя
  безопасно отделить от посторонних пользовательских правок.

## История сессии

Этот раздел фиксирует ключевые решения и ход работы, чтобы восстановить контекст при перезапуске opencode.

### Сессия 1 (2026-07-31): Создание лаунчера

**Заказчик:** приватный сервер WoW (1.12 / 3.3.5a).
**Требования:**
- GUI-приложение на Python под Windows
- Обновление клиента WoW в папке запуска
- GUI: PyQt5 (тёмная тема)
- Источник обновлений: HTTP/FTP → фолбэк BitTorrent (libtorrent)
- Лаунчер называется `Dreamworld.exe`, игровой клиент — `Wow.exe`
- Иконка: сгенерированная, буква «D» золотом на тёмно-синем фоне, 9 размеров (16–1024)
- Сборка .exe через GitHub Actions (Wine на Apple Silicon не работает — QEMU падает)
- Самообновление лаунчера: фоновая проверка при запуске, тихая если нет/ошибка, диалог при наличии, замена через bat-скрипт

**Принятые решения:**
- venv в `.venv/` (не `--break-system-packages`)
- GitHub: приватный репо `amatol/wow-launcher`, HTTPS (не SSH — ключ не настроен)
- `gh` CLI установлен через Homebrew, авторизован с scope `workflow`
- ICO > 256px: Pillow не поддерживает, упаковка PNG-в-ICO вручную в `generate_icon.py`
- Manifest лаунчера: отдельный `launcher_manifest.json` (не `manifest.json` клиента)
- Самообновление лаунчера: rename-then-replace (без bat-скрипта), отложенная очистка при следующем запуске

**Состояние:**
- Все задачи выполнены, CI зелёный
- `dist/Dreamworld.exe` — 36 MB, PE32+ x86-64, собран через GitHub Actions
- Репо: https://github.com/amatol/wow-launcher (private)
- Runs: 3 (1 fail — UTF-8, 2 success)

### Сессия 2 (2026-07-31): подготовка рабочей инфраструктуры

- Репозиторий клонирован на сервер в `/root/launcher`, GitHub CLI авторизован.
- Публичная точка обновлений выбрана как
  `https://wotlk.amatol.blog/launcher/`; DNS уже указывает на игровой сервер,
  но nginx, TLS и firewall для 80/443 ещё не настроены.
- Лаунчер называется `Dreamworld.exe`, а игровой бинарник — только `Wow.exe`
  (с допустимыми вариантами регистра).
- Добавлены проверка путей и метаданных манифеста, серверные генераторы
  манифестов, nginx-шаблон, тесты и `docs/SERVER.md`.
- Эталонный WoW-клиент на сервере отсутствует; без него рабочий клиентский
  манифест и набор файлов создать нельзя. Клиент загружается в
  `/opt/azerothcore/client`; пользователь сообщит о завершении.
- На сервере развёрнут nginx, открыт TCP 80/443 и выпущен автоматически
  продлеваемый сертификат Let's Encrypt для `wotlk.amatol.blog`.
- Клиент build 12340 проверен и опубликован: 171 файл, 17 796 710 014 байт.
  Единственная копия находится в `/opt/azerothcore/client`, а
  `/srv/dreamworld-launcher/files` является ссылкой на неё. Клиентский
  манифест версии `20260731` доступен по HTTPS; исключён только `Repair.log`.
- Windows CI run `30661252739` успешно собрал и опубликовал лаунчер
  `Dreamworld.exe` версии `20260731`; полный HTTPS-download проверен по
  SHA-256. Следующая обязательная проверка выполняется на реальной Windows.

## Purpose

Графический лаунчер для приватного сервера WoW. Обновляет файлы клиента в папке запуска. Самообновляется через bat-скрипт.

## Architecture

```
main.py                 — точка входа, QApplication + иконка
config.py               — Config: пути, URL, таймауты, версия лаунчера
manifest.json           — пример манифеста обновлений клиента
launcher_manifest.json  — пример манифеста обновлений лаунчера
news.json               — пример новостей сервера
generate_icon.py        — генерация dreamworld.ico (D, золото, 16–1024px)
Dreamworld.spec         — PyInstaller spec (onefile, windowed, icon)
core/
  version.py            — поиск/запуск Dreamworld.exe, версии патча
  self_update.py        — фоновая проверка, скачивание, rename-then-replace, очистка
updater/
  manifest.py           — парсинг JSON-манифеста, SHA-256 проверка
  http_updater.py       — HTTP-скачивание + бэкап .bak
  torrent_updater.py    — BitTorrent фолбэк (libtorrent, optional)
  addons.py             — манифест аддонов, установка/обновление из каталогов
ui/
  main_window.py        — главное окно, UpdateWorker, SelfUpdateWorker, SelfUpdateDialog
  widgets.py            — NewsWidget, NewsWorker, ProgressWidget
  addons_dialog.py      — диалог управления аддонами (чекбоксы, установка, прогресс)
assets/
  dreamworld.ico        — иконка (9 размеров, PNG-в-ICO для >256)
.github/workflows/
  build.yml             — CI: windows-latest, Python 3.10, PyInstaller
```

## Key Flows

### Обновление клиента
1. `Config.GAME_DIR` = папка запуска (через `sys.executable` если frozen)
2. Качает `manifest.json` с `MANIFEST_URL`
3. **Всегда** проверяет каждый файл из манифеста по размеру и SHA-256 на диске
4. Если файл уже существует и хэш совпадает — пропускает
5. Иначе HTTP скачивание недостающих/изменённых файлов → если fail → BitTorrent
6. Бэкап `.bak` перед заменой, проверка хэша после
7. Записывает новую версию в `.launcher_version`

### Самообновление лаунчера
1. Фоновый поток `SelfUpdateWorker` качает `launcher_manifest.json`
2. Сравнивает version с `Config.LAUNCHER_VERSION`
3. Нет обновления / ошибка сети → **тихо, без UI**
4. Есть обновление → `SelfUpdateDialog` («Обновить» / «Позже»)
5. При согласии → скачивание в `%TEMP%` → проверка SHA-256 и размера
6. Rename-then-replace: текущий `Dreamworld.exe` → `Dreamworld.exe.old`,
   новый ставится на его место, запускается новый процесс
7. При следующем запуске `cleanup_self_update_files` удаляет `.old` и прочий мусор

### Сборка .exe
1. Пуш в main → GitHub Actions `build.yml`
2. windows-latest, Python 3.10, `pip install -r requirements.txt`
3. `python generate_icon.py` → генерация иконки
4. `pyinstaller Dreamworld.spec --noconfirm`
5. Артефакт `Dreamworld-exe` → скачать через `gh run download`
6. **Wine на Apple Silicon не работает** (QEMU assertion failure) — только CI

## Conventions

- **venv**: `.venv/` в корне, НЕ `--break-system-packages`
- **Кодировка**: `PYTHONUTF8=1` в CI для кириллицы в print
- **Иконка**: генерируется `generate_icon.py`, не хардкодится; Pillow не пишет ICO >256, поэтому PNG-в-ICO вручную через `struct`
- **GUI**: тёмная тема `#0f0f23`, акцент `#e94560`, шрифт Segoe UI 18 bold
- **Имена**: игровой клиент = `Wow.exe`, лаунчер = `Dreamworld.exe`
- **Версии лаунчера**: YYYYMMDD; не более одного выпуска в день, числовое сравнение
- **Manifest лаунчера**: `version`, `download_url`, `sha256`, `size`, `changelog`
- **gh CLI**: авторизован как `amatol`, scope `workflow`, протокол HTTPS
