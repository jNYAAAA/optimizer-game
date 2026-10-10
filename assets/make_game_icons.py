"""Логотипы игр для вкладки «Оптимизация игр» (стилизованные метки)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SIZE = 512
FONT_PATH = r"C:\Windows\Fonts\segoeuib.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def rounded(bg, border) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 24
    d.rounded_rectangle([m, m, SIZE - m, SIZE - m], radius=110, fill=bg, outline=border, width=10)
    return img


def centered_text(img: Image.Image, text: str, color, size: int = 260) -> None:
    d = ImageDraw.Draw(img)
    font = _font(size)
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((SIZE - w) / 2 - box[0], (SIZE - h) / 2 - box[1]), text, font=font, fill=color)


def cs2() -> Image.Image:
    img = rounded((27, 31, 39, 255), (245, 166, 35, 255))
    d = ImageDraw.Draw(img)
    cx = cy = SIZE / 2
    r = 150
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(245, 166, 35, 255), width=14)
    gap, length = 44, 96
    for a, b in (
        ((cx, cy - r - length), (cx, cy - gap)),
        ((cx, cy + gap), (cx, cy + r + length)),
        ((cx - r - length, cy), (cx - gap, cy)),
        ((cx + gap, cy), (cx + r + length, cy)),
    ):
        d.line([a, b], fill=(240, 240, 240, 255), width=16)
    d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(245, 166, 35, 255))
    return img


def dota2() -> Image.Image:
    img = rounded((24, 20, 18, 255), (194, 60, 42, 255))
    centered_text(img, "D2", (220, 70, 50, 255))
    return img


def apex() -> Image.Image:
    img = rounded((22, 24, 28, 255), (218, 41, 42, 255))
    d = ImageDraw.Draw(img)
    cx = SIZE / 2
    d.polygon([(cx, 120), (cx + 150, 392), (cx, 330), (cx - 150, 392)], fill=(218, 41, 42, 255))
    d.polygon([(cx, 190), (cx + 84, 356), (cx, 322), (cx - 84, 356)], fill=(22, 24, 28, 255))
    return img


def pubg() -> Image.Image:
    img = rounded((20, 20, 20, 255), (242, 169, 0, 255))
    d = ImageDraw.Draw(img)
    cx = SIZE / 2
    d.arc([cx - 170, 140, cx + 170, 420], start=180, end=360, fill=(242, 169, 0, 255), width=34)
    d.rectangle([cx - 170, 280, cx + 170, 340], fill=(242, 169, 0, 255))
    d.rectangle([cx - 60, 340, cx + 60, 400], fill=(242, 169, 0, 255))
    return img


def main() -> None:
    for name, builder in (("cs2", cs2), ("dota2", dota2), ("apex", apex), ("pubg", pubg)):
        builder().resize((128, 128), Image.LANCZOS).save(HERE / f"{name}.png")
    print("saved cs2.png, dota2.png, apex.png, pubg.png")


if __name__ == "__main__":
    main()
