# Сервер обновлений Dreamworld Launcher

## Схема

Статические файлы публикуются по HTTPS из `/srv/dreamworld-launcher`:

```text
/srv/dreamworld-launcher/
├── manifest.json
├── launcher_manifest.json
├── news.json              # генерируется из Breaking News игрового сервера
├── addons_manifest.json   # публикуется последним после ZIP аддонов
├── addons/                # проверенные ZIP-архивы аддонов
├── Dreamworld.exe          # лаунчер
└── files -> /opt/azerothcore/client
```

Лаунчер обращается к `https://wotlk.amatol.blog/launcher/`. Веб-сервер не
имеет доступа к MySQL, AzerothCore, SOAP или Telegram-боту: интеграция с ними
для раздачи обновлений не требуется.

## Подготовка клиентского манифеста

Единственная эталонная копия клиента хранится в `/opt/azerothcore/client` и
доступна nginx через ссылку `/srv/dreamworld-launcher/files`. Она должна
содержать корректный `realmlist.wtf` для
`wotlk.amatol.blog` (realm работает на стандартном auth-порту 3724). Файлы
клиента нельзя добавлять в Git.

```bash
python tools/generate_manifest.py /path/to/clean-client /tmp/manifest.json \
  --version 20260731
```

Скрипт вычисляет размер и SHA-256 каждого файла. Служебные файлы лаунчера,
временные загрузки и резервные копии исключаются.

После любого изменения файлов эталонного клиента необходимо заново создать и
атомарно опубликовать `manifest.json`. Иначе nginx начнёт отдавать изменённые
файлы со старыми контрольными суммами.

## Подготовка самообновления

После успешной сборки Windows-артефакта:

```bash
python tools/generate_launcher_manifest.py dist/Dreamworld.exe \
  /tmp/launcher_manifest.json --version 20260731 \
  --changelog "Описание выпуска"
```

Только при переходе с прежней десятизначной схемы используется одноразовый
параметр `--legacy-sequence 0`. Он публикует мост `YYYYMMDD00`, сохраняя
встроенную версию EXE в формате `YYYYMMDD`.

Сначала публикуется лаунчер `Dreamworld.exe`, затем соответствующий манифест.
Клиентский `manifest.json` также заменяется последним: это не позволит
лаунчеру увидеть версию раньше, чем все файлы будут доступны.

## Аддоны

Исходный каталог должен содержать по одной папке на аддон; имя папки должно
совпадать с именем аддона и внутри неё нужен верхнеуровневый `.toc`. Генератор
не создаёт пустой манифест и формирует ZIP с обязательной корневой папкой:

```bash
python tools/generate_addons_manifest.py /path/to/addons /tmp/addons \
  /tmp/addons_manifest.json --version 20260802
```

Сначала скопировать ZIP из `/tmp/addons/` в
`/srv/dreamworld-launcher/addons/`, проверить их скачивание по HTTPS и только
затем атомарно заменить `/srv/dreamworld-launcher/addons_manifest.json`.
Контрольные суммы и размеры обязательны: лаунчер отвергает неполные записи.

## Веб-сервер и TLS

Шаблон `deploy/nginx-dreamworld-launcher.conf` публикует только GET/HEAD.
nginx установлен и включён, TCP 80/443 разрешены в постоянной конфигурации
nftables. Сертификат Let's Encrypt для `wotlk.amatol.blog` выпущен, а его
автоматическое продление выполняет активный `certbot.timer`. Корень сайта
возвращает 404; рабочие файлы доступны только под `/launcher/`.

## Границы интеграции

- `/root/wowserver` определяет адрес realm и клиентскую сборку 12340, но не
  должен раздавать файлы или принимать команды лаунчера.
- `/root/telegrambot` может публиковать пользователям ссылку на готовый
  лаунчер `Dreamworld.exe` или архив клиента; его локальный защищённый API не
  следует открывать наружу.
- Полный клиент 3.3.5a и его лицензирование/право распространения должен
  предоставить владелец сервера. В текущей системе эталонного клиента нет.

## Новости

Единый источник новостей — управляемая страница
`/root/wowserver/config/breaking-news/breakingnews.html`, которую использует
модуль Breaking News на экране выбора персонажа. Команда
`/root/wowserver/scripts/publish-breaking-news.sh` одновременно обновляет
страницу модуля и атомарно создаёт `/srv/dreamworld-launcher/news.json` для
лаунчера. Она также вызывается штатным `deploy-azerothcore.sh`.

После редактирования страницы новости публикуются без полной пересборки:

```bash
sudo /root/wowserver/scripts/publish-breaking-news.sh
```
