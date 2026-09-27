# Источники ресурсов нового оформления

## Иллюстрация northrend.png

Создана 27.09.2026 встроенным инструментом image_gen (не CLI/API fallback).
Оригинал сохранён в /root/.codex/generated_images/01a0e494-43ce-7c12-8a1a-e48591adfd69/exec-ca850930-568c-4e69-a6d1-eccdf04e2d16.png.
В проект скопирован без редактирования. Это иллюстрация для фона, не скриншот игры.

Точный промпт:

> Create a premium dark fantasy environmental key art background for a World of Warcraft Wrath of the Lich King desktop game launcher. Landscape 1536x1024. A towering intricate icy gothic citadel at the far RIGHT third, jagged frozen cliffs, a glacial valley and distant snowy mountains, sparse drifting snow, moonlit arctic blue, deep midnight navy shadows, beautifully painted cinematic game concept art with convincing detailed ice and stone, not photoreal. Composition: left half mostly quiet deep navy atmospheric mist with low contrast, all impressive architecture and light concentrated upper right and right third. Bottom quarter dark mist. Restrained desaturated pale blue light, a tiny warm amber window in the fortress. No characters, no text, no logos, no lettering, no interface, no buttons. Artwork must read well as a dark backdrop behind interface labels, elegant atmospheric depth, rich hand-painted detail. Asset for real launcher, not a mockup.

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
