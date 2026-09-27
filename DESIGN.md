---
name: Dreamworld Launcher — Нордскол
description: Атмосфера WotLK в настольном лаунчере
colors:
  primary: "#ddba7c"
  primary-text: "#18212a"
  primary-hover: "#f0d4a5"
  background: "#091521"
  surface: "#102331"
  button: "#142b3b"
  button-text: "#dce9f0"
  foreground: "#e4edf2"
  secondary: "#b7cedd"
  metadata: "#9db5c6"
  ice: "#76bfd5"
  focus: "#b9e8f7"
  progress-text-fill: "#315c70"
typography:
  display:
    fontFamily: Cinzel
    fontSize: 34px
  display-compact:
    fontFamily: Cinzel
    fontSize: 22px
  body:
    fontFamily: "Segoe UI, DejaVu Sans"
    fontSize: 14px
  primary-button:
    fontFamily: "Segoe UI, DejaVu Sans"
    fontSize: 18px
    fontWeight: 700
  status:
    fontFamily: "Segoe UI, DejaVu Sans"
    fontSize: 12px
rounded:
  button: 5px
  panel: 6px
  progress: 4px
spacing:
  compact: 8px
  control-gap: 10px
  normal: 14px
  column-gap: 28px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-text}"
    typography: "{typography.primary-button}"
    rounded: "{rounded.button}"
    padding: 8px 16px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.button}"
    textColor: "{colors.button-text}"
    typography: "{typography.body}"
    rounded: "{rounded.button}"
    padding: 8px 16px
  progress-with-text:
    backgroundColor: "{colors.progress-text-fill}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.progress}"
---

# Дизайн лаунчера: Нордскол

## Overview

**Creative North Star: "Нордскол / WotLK"**

Пользователь подтвердил «Атмосфера WotLK». Иллюстрация ледяной цитадели создаёт атмосферу, а управление сохраняет привычные настольные кнопки и диалоги. Декоративной анимации нет.

**Key Characteristics:**

- Ледяная цитадель на тёмном фоне.
- Золотое основное действие и светлый текст.
- Общая тема главного окна и диалогов.

## Colors

Золото выделяет основное действие; ледяной акцент сопровождает загрузку.
Тёмные нейтральные поверхности поддерживают светлый основной и вторичный текст.
Нормативные значения находятся в YAML выше; исходник темы — `ui/theme.py`.
В диалогах заполнение прогресса темнее, чтобы светлый процент оставался читаемым.

## Typography

Заголовок использует локальный `assets/fonts/Cinzel.ttf`; в компактном окне
применяется роль display-compact. Остальной интерфейс — Segoe UI с запасным
DejaVu Sans. Заголовки новостей — 17px bold, даты — 12px, версии внизу — 11px.
Происхождение ресурсов и промпт иллюстрации: `assets/SOURCES.md`.
Шрифт и `assets/northrend.png` включены в `Dreamworld.spec`; при запуске
не требуют сети. Заголовок остаётся текстом, а не частью картинки.

## Layout

Главное окно: 1000×560 по умолчанию, минимум 720×400 логических пикселей Qt.
Новости занимают растяжимую левую колонку, действия — правую шириной 230px;
между ними column-gap. Кнопки запуска и отмены имеют высоту 56px,
«Аддоны» и «Аккаунт» — 40px. Статус, полоса и версии размещены ниже.

При ширине <850 или высоте <500 заголовок становится однострочным,
подзаголовок скрывается. Отступы окна слева/сверху/справа/снизу меняются
с 28/22/28/18 на 18/14/18/12px, вертикальный интервал — с normal на compact.
Диалог аддонов: 720×600, минимум 680×480; самообновления: 540×320,
минимум 480×260; аккаунта: фиксированные 470×240.

## Elevation & Depth

Глубину создают иллюстрация, затемняющие градиенты и тональные поверхности;
тени и размытие фона не применяются. Панель новостей использует почти
непрозрачный фон rgba(9, 21, 33, 220) в синтаксисе Qt QSS.
Растр масштабируется с сохранением пропорций и кэшируется при изменении
размера; верхний и правый края изображения сохраняются.

## Shapes

Кнопки и панели используют небольшие скругления из YAML.
Полосы имеют радиус progress; их заполнение — 3px. Индикаторы флажков
имеют размер 18×18px с границей 1px и радиусом 3px.

## Components

Общая тема применяется к главному окну, аддонам, аккаунту и самообновлению.
Кнопки поддерживают hover, pressed, disabled и видимый клавиатурный фокус:
обычный фокус — рамка 2px цвета focus, основной — белая рамка 2px.

Основная кнопка сохраняет состояния «Играть», «Обновить», «Скачать клиент»;
при загрузке на её месте появляется «Отмена». Клиент считается установленным
по `Config.has_complete_client_layout()`, а не наличию одного Wow.exe.

Новости прокручиваются, показывают не более пяти записей и открывают
внешние ссылки. Длинный статус операции переносится в области высотой
до 36px; полный текст доступен через подсказку. Главная полоса высотой
8px не содержит текста: процент 1–99 вынесен над ней. Полосы диалогов
сохраняют процент внутри. У флажков аддонов есть явная галочка.

HTML/CSS-примеры в `.impeccable/design.json` — переносимые иллюстрации
нативных компонентов для панели документации, не код интерфейса PyQt5.

## Do's and Don'ts

- Do сохранять читаемую подложку новостей поверх иллюстрации.
- Do использовать тёмное заполнение полосы, если процент показан внутри.
- Do сохранять видимый клавиатурный фокус кнопок.
- Don't помещать Cinzel в основной текст интерфейса.
- Don't добавлять декоративные фоновые таймеры.
