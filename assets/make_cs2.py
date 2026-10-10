"""Логотип CS2 для вкладки «Оптимизация игр» (стилизованный прицел)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZE = 512
BG = (27, 31, 39, 255)
ORANGE = (245, 166, 35, 255)
WHITE = (240, 240, 240, 255)


def build() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    m = 24
    d.rounded_rectangle([m, m, SIZE - m, SIZE - m], radius=110, fill=BG, outline=ORANGE, width=10)

    cx = cy = SIZE / 2
    r = 150
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ORANGE, width=14)

    gap, length = 44, 96
    d.line([cx, cy - r - length, cx, cy - gap], fill=WHITE, width=16)
    d.line([cx, cy + gap, cx, cy + r + length], fill=WHITE, width=16)
    d.line([cx - r - length, cy, cx - gap, cy], fill=WHITE, width=16)
    d.line([cx + gap, cy, cx + r + length, cy], fill=WHITE, width=16)

    dot = 20
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=ORANGE)
    return img


def main() -> None:
    build().resize((128, 128), Image.LANCZOS).save(HERE / "cs2.png")
    print("saved cs2.png")


if __name__ == "__main__":
    main()
