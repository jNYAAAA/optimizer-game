"""Баннеры для установщика Inno Setup в стиле приложения."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "installer"
OUT.mkdir(exist_ok=True)
FONT_PATH = r"C:\Windows\Fonts\segoeuib.ttf"

BG = (6, 7, 12)
PANEL = (13, 16, 25)
ACCENT = (34, 224, 255)
TEXT_DIM = (93, 116, 132)


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def _moon(size: int) -> Image.Image:
    icon = Image.open(HERE / "icon.png").convert("RGBA")
    return icon.resize((size, size), Image.LANCZOS)


def banner() -> Image.Image:
    w, h = 164, 314
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 4], fill=ACCENT)
    d.rectangle([0, 4, w, 5], fill=PANEL)

    moon = _moon(104)
    img.paste(moon, ((w - 104) // 2, 46), moon)

    title_font = _font(19)
    for i, line in enumerate(("OPTIMIZER", "GAME")):
        box = d.textbbox((0, 0), line, font=title_font)
        x = (w - (box[2] - box[0])) / 2 - box[0]
        d.text((x, 176 + i * 24), line, font=title_font, fill=ACCENT)

    small = _font(11)
    for i, line in enumerate(("характеристики", "и оптимизация", "Windows")):
        box = d.textbbox((0, 0), line, font=small)
        x = (w - (box[2] - box[0])) / 2 - box[0]
        d.text((x, 232 + i * 15), line, font=small, fill=TEXT_DIM)

    d.rectangle([0, h - 4, w, h], fill=ACCENT)
    return img


def small_image() -> Image.Image:
    s = 55
    img = Image.new("RGB", (s, s), BG)
    moon = _moon(40)
    img.paste(moon, ((s - 40) // 2, (s - 40) // 2), moon)
    return img


def main() -> None:
    banner().save(OUT / "wizard.bmp")
    small_image().save(OUT / "wizard_small.bmp")
    print("saved wizard.bmp, wizard_small.bmp")


if __name__ == "__main__":
    main()
