"""
Генерация иконки в стиле WoW для Dreamworld.exe.
Золотая буква 'D' на тёмно-синем фоне с декоративной рамкой.

Pillow не сохраняет размеры > 256 в ICO, поэтому для 512 и 1024
мы упаковываем PNG вручную в формат ICO (PNG-в-ICO).
"""
import io
import os
import struct
from PIL import Image, ImageDraw, ImageFont


ICO_MAX_PIL = 256  # Pillow сохраняет ICO максимум до этого размера


def find_font(size):
    candidates = [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Тёмно-синий фон с градиентом
    bg_outer = (15, 20, 40, 255)
    bg_inner = (30, 40, 80, 255)

    margin = max(1, size // 32)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 8,
        fill=bg_outer,
    )

    # Градиент (упрощённый — концентрические прямоугольники)
    steps = size // 4
    for i in range(steps):
        t = i / steps
        r = int(bg_inner[0] * (1 - t) + bg_outer[0] * t)
        g = int(bg_inner[1] * (1 - t) + bg_outer[1] * t)
        b = int(bg_inner[2] * (1 - t) + bg_outer[2] * t)
        inset = margin + size // 16 + i * (size // 4) // steps
        draw.rounded_rectangle(
            [inset, inset, size - inset, size - inset],
            radius=max(2, size // 8 - i),
            fill=(r, g, b, 255),
        )

    # Золотая рамка
    gold = (200, 160, 60, 255)
    gold_light = (255, 215, 120, 255)
    border = max(1, size // 48)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 8,
        outline=gold,
        width=border,
    )
    # Внутренняя рамка (тоньше, светлее)
    inner_margin = margin + border + max(1, size // 64)
    draw.rounded_rectangle(
        [inner_margin, inner_margin, size - inner_margin, size - inner_margin],
        radius=max(2, size // 8 - border),
        outline=gold_light,
        width=max(1, border // 2),
    )

    # Буква D
    font_size = int(size * 0.6)
    font = find_font(font_size)

    text = "D"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1]

    # Тень
    shadow_offset = max(1, size // 64)
    draw.text((tx + shadow_offset, ty + shadow_offset), text,
              fill=(0, 0, 0, 160), font=font)

    # Буква золотым
    draw.text((tx, ty), text, fill=gold_light, font=font)

    return img


def _png_bytes(img: Image.Image) -> bytes:
    """Конвертировать изображение в PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_ico(sizes: list, path: str):
    """
    Собрать ICO вручную, поддерживая размеры > 256 через PNG-в-ICO.
    Формат ICO: ICONDIR + ICONDIRENTRY[] + данные.
    Для <= 256 — BMP-данные (Pillow), для > 256 — PNG-данные.
    """
    pil_sizes = [s for s in sizes if s <= ICO_MAX_PIL]
    big_sizes = [s for s in sizes if s > ICO_MAX_PIL]

    # Сгенерировать все изображения
    entries = []  # (width, height, data_bytes, is_png)

    for s in pil_sizes:
        img = draw_icon(s)
        buf = io.BytesIO()
        img.save(buf, format="ICO", sizes=[(s, s)])
        ico_data = buf.getvalue()
        # Извлечь BMP-данные из single-size ICO
        _reserved, _type, count = struct.unpack_from("<HHH", ico_data, 0)
        if count == 1:
            _w, _h, _c, _r, _p, _b, size, off = struct.unpack_from("<BBBBHHII", ico_data, 6)
            raw = ico_data[off:off + size]
            entries.append((s, s, raw, False))

    for s in big_sizes:
        img = draw_icon(s)
        png_data = _png_bytes(img)
        entries.append((s, s, png_data, True))

    # Собрать ICO
    num = len(entries)
    header = struct.pack("<HHH", 0, 1, num)  # ICONDIR

    dir_offset = 6 + num * 16  # после header + directory
    data_offset = dir_offset
    directory = b""
    data_blob = b""

    for w, h, raw, is_png in entries:
        size = len(raw)
        # В ICONDIRENTRY ширина/высота 0 = 256, но 512/1024 не помещаются в байт
        # Для PNG-entries > 256 тоже пишем 0 (=256), Windows читает размер из PNG
        w_byte = w if w < 256 else 0
        h_byte = h if h < 256 else 0
        directory += struct.pack("<BBBBHHII", w_byte, h_byte, 0, 0, 1, 32, size, data_offset)
        data_blob += raw
        data_offset += size

    with open(path, "wb") as f:
        f.write(header)
        f.write(directory)
        f.write(data_blob)


def generate_icon(path: str):
    """
    Сгенерировать .ico с разрешениями 16..1024.
    Размеры 512 и 1024 упаковываются как PNG-в-ICO.
    """
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    _build_ico(sizes, path)

    print(f"Иконка сохранена: {path}")
    print(f"  Размер файла: {os.path.getsize(path)} байт")

    # Проверка структуры
    with open(path, "rb") as f:
        data = f.read()
    _r, _t, count = struct.unpack_from("<HHH", data, 0)
    print(f"  Фреймов в ICO: {count}")
    off = 6
    for i in range(count):
        w, h, _c, _res, _p, bpp, sz, doff = struct.unpack_from("<BBBBHHII", data, off)
        w = w if w != 0 else 256
        h = h if h != 0 else 256
        print(f"  [{i}] {w}x{h}, bpp={bpp}, size={sz}")
        off += 16

    # PNG 1024 для предпросмотра
    preview = draw_icon(1024)
    preview_path = os.path.splitext(path)[0] + "_preview.png"
    preview.save(preview_path)
    print(f"Предпросмотр: {preview_path}")


if __name__ == "__main__":
    generate_icon(os.path.join(os.path.dirname(__file__), "assets", "dreamworld.ico"))
