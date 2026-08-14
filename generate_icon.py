"""Сборка многослойной Windows-иконки из launcher_icon.png."""
import io
import os
import struct
from PIL import Image


ICO_MAX_PIL = 256  # Pillow сохраняет ICO максимум до этого размера


def load_source(path: str) -> Image.Image:
    """Загрузить квадратный RGBA-исходник без изменения его дизайна."""
    with Image.open(path) as source:
        source.load()
        if source.width != source.height:
            raise ValueError(f"Icon source must be square: {source.size}")
        return source.convert("RGBA")


def resize_icon(source: Image.Image, size: int) -> Image.Image:
    """Масштабировать исходник с качественной фильтрацией и alpha-каналом."""
    return source.resize((size, size), Image.Resampling.LANCZOS)


def _png_bytes(img: Image.Image) -> bytes:
    """Конвертировать изображение в PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_ico(source: Image.Image, sizes: list, path: str):
    """
    Собрать ICO вручную, поддерживая размеры > 256 через PNG-в-ICO.
    Формат ICO: ICONDIR + ICONDIRENTRY[] + данные.
    Для <= 256 — BMP-данные (Pillow), для > 256 — PNG-данные.
    """
    pil_sizes = [s for s in sizes if s <= ICO_MAX_PIL]
    big_sizes = [s for s in sizes if s > ICO_MAX_PIL]

    # Собрать все размеры из одного эталонного исходника.
    entries = []  # (width, height, data_bytes, is_png)

    for s in pil_sizes:
        img = resize_icon(source, s)
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
        img = resize_icon(source, s)
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


def generate_icon(source_path: str, output_path: str):
    """
    Сгенерировать .ico с разрешениями 16..1024.
    Размеры 512 и 1024 упаковываются как PNG-в-ICO.
    """
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    source = load_source(source_path)
    _build_ico(source, sizes, output_path)

    print(f"Icon source: {source_path} ({source.width}x{source.height})")
    print(f"Icon saved: {output_path}")
    print(f"  File size: {os.path.getsize(output_path)} bytes")

    # Проверка структуры
    with open(output_path, "rb") as f:
        data = f.read()
    _r, _t, count = struct.unpack_from("<HHH", data, 0)
    print(f"  ICO frames: {count}")
    off = 6
    for i in range(count):
        w, h, _c, _res, _p, bpp, sz, doff = struct.unpack_from("<BBBBHHII", data, off)
        w = w if w != 0 else 256
        h = h if h != 0 else 256
        print(f"  [{i}] {w}x{h}, bpp={bpp}, size={sz}")
        off += 16

    # PNG 1024 для предпросмотра
    preview = resize_icon(source, 1024)
    preview_path = os.path.splitext(output_path)[0] + "_preview.png"
    preview.save(preview_path)
    print(f"Preview: {preview_path}")


if __name__ == "__main__":
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    generate_icon(
        os.path.join(assets_dir, "launcher_icon.png"),
        os.path.join(assets_dir, "dreamworld.ico"),
    )
