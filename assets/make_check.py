"""Генерация PNG-галочек для чекбоксов (стиль Windows 11).

Создаёт assets/check_white.png (для светлого акцента) и
assets/check_dark.png (для светлого акцента в тёмной теме).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SUPER = 256          # рисуем крупно и уменьшаем (сглаживание)
FINAL = 16           # итоговый размер для QSS


def build(color: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (SUPER, SUPER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = SUPER / 16.0
    points = [
        (3.0 * scale, 8.4 * scale),
        (6.4 * scale, 11.8 * scale),
        (13.0 * scale, 4.4 * scale),
    ]
    width = int(2.0 * scale)
    draw.line(points, fill=color, width=width, joint="curve")
    # скруглим концы
    for x, y in (points[0], points[-1]):
        r = width / 2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    return image.resize((FINAL, FINAL), Image.LANCZOS)


def main() -> None:
    build((255, 255, 255, 255)).save(HERE / "check_white.png")
    build((0, 58, 92, 255)).save(HERE / "check_dark.png")
    print("saved check_white.png, check_dark.png")


if __name__ == "__main__":
    main()
