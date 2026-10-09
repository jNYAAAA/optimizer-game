"""Optimizer Game — точка входа приложения.

Запуск:
    python main.py
"""
from __future__ import annotations

import sys

from app.admin import auto_elevate

if __name__ == "__main__":
    # Приложение всегда работает с правами администратора: если их нет,
    # запрашиваем UAC и перезапускаемся.
    if auto_elevate():
        sys.exit(0)

    from app.ui.main_window import run

    sys.exit(run())
