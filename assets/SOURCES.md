# Источники ресурсов нового оформления

## Иллюстрация northrend.png

Создана 01.10.2026 встроенным инструментом image_gen (не CLI/API fallback).
Референс пользователя amatol.PNG использован только для стилистики пиксель-арта;
лицо, человек и очки не перенесены. Сам референс не включён в Git или EXE.
Оригинал: /root/.codex/generated_images/01a0f8e1-8c1c-74d1-a669-6c000f60e03f/exec-295ec95a-87ac-4583-86a5-b5a23538d5d2.png.
В проект скопирован без редактирования. Это фон, не скриншот игры.

Точный промпт:

> Use case: stylized-concept. Create a new landscape background asset for the Dreamworld Wrath of the Lich King desktop launcher, wide 16:9. Reference image is STYLE ONLY: match its deliberately coarse pixel art, large hard square pixels, flat limited palette, crisp stepped silhouettes and simple shaded clusters. Do NOT include the person, portrait, face, glasses, human, character or any likeness. Scene: a glacial Northrend valley with snow-covered angular mountains, frozen lake, and an imposing dark icy gothic citadel concentrated in the upper right third. Midnight blue and muted sky blue ice with restrained warm gold window pixels. Quiet dark blue atmospheric negative space across the left half for the news panel and along the top for a single line heading. Pixel art landscape, old school adventure-game background, clearly visible coarse pixels like the supplied image; no smooth painting, no anti-aliasing, no realistic textures. Bottom quarter dark. No text, logos, buttons, frames or UI. Save the output image to disk and return its path.

## Шрифт

Cinzel: https://github.com/google/fonts/tree/main/ofl/cinzel,
ветка main, проверенная ревизия 23e54b51ddffbc7713c583748e3bd86f62b1fa4a.
Исходный Cinzel[wght].ttf сохранён как fonts/Cinzel.ttf без изменения;
лицензия SIL Open Font License 1.1 — fonts/OFL-Cinzel.txt, поставляется с EXE.
В тексте лицензии удалён один концевой пробел, содержание сохранено.

## Векторный флажок

check.svg создан для этого интерфейса как простой векторный знак выбора.
Иконка приложения dreamworld.ico сохранена прежней.

## Подключённые навыки

Установлены skill-installer в /root/.codex/skills:

- frontend-design: https://github.com/anthropics/skills, main,
  33375500bcea98d610eb30ce10ac4e59b89c390d, путь skills/frontend-design.
- impeccable: https://github.com/pbakaus/impeccable, main,
  9d715cc4f5564a990ca8345abfdd5df6dc9b41c8, путь plugin/skills/impeccable.

Установка: python3 /root/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py
с --repo и --path, указанными выше. Для scripts/impeccable восстановлен chmod +x
после распаковки. Навыки не включаются в EXE и не являются зависимостью лаунчера.
