"""Генерация иконки приложения (киберпанк-минимализм).

Рисует луну в скруглённом квадрате и сохраняет многоразмерный .ico
и PNG-превью. Запуск: ``python assets/make_icon.py``.
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
HERE = Path(__file__).resolve().parent

BG = (10, 13, 20, 255)          # почти чёрный фон
PANEL = (17, 22, 33, 255)
ACCENT = (34, 224, 255, 255)    # неоновый циан
ACCENT_DIM = (18, 167, 196, 255)
MAGENTA = (255, 46, 151, 255)


def build_image() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = 64
    radius = 220

    # Основной скруглённый квадрат
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=radius,
        fill=BG,
        outline=ACCENT,
        width=24,
    )
    # Внутренняя тонкая рамка
    draw.rounded_rectangle(
        [margin + 46, margin + 46, SIZE - margin - 46, SIZE - margin - 46],
        radius=radius - 34,
        outline=(18, 167, 196, 130),
        width=6,
    )

    # Луна рисуется на отдельном слое, чтобы «вырез» не трогал квадрат
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    cx, cy, r = SIZE / 2, SIZE / 2 + 12, 250
    layer_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    cut_dx, cut_dy = r * 0.44, -r * 0.44
    layer_draw.ellipse(
        [cx - r + cut_dx, cy - r + cut_dy, cx + r + cut_dx, cy + r + cut_dy],
        fill=(0, 0, 0, 0),
    )
    image.alpha_composite(layer)

    # Небольшая маджента-точка как акцент
    dot = 46
    dx, dy = SIZE - margin - 196, margin + 150
    draw.ellipse([dx, dy, dx + dot, dy + dot], fill=MAGENTA)

    return image


def main() -> None:
    image = build_image()

    ico_path = HERE / "icon.ico"
    image.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    png_path = HERE / "icon.png"
    image.resize((512, 512), Image.LANCZOS).save(png_path)

    print("saved", ico_path)
    print("saved", png_path)


if __name__ == "__main__":
    main()
