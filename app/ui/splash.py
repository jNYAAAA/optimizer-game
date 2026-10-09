"""Анимированный экран загрузки (splash) в стиле приложения."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSplashScreen

from ..config import APP_DISPLAY_NAME, APP_VERSION
from . import theme


class SplashScreen(QSplashScreen):
    """Полупрозрачная карточка с логотипом, прогрессом и статусом."""

    WIDTH = 560
    HEIGHT = 320

    def __init__(self) -> None:
        self._progress = 0.0
        self._phase = 0.0
        self._message = "Инициализация…"
        super().__init__(self._render(), Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def update_progress(
        self, value: float, phase: float = 0.0, message: str | None = None
    ) -> None:
        self._progress = max(0.0, min(value, 100.0))
        self._phase = phase
        if message:
            self._message = message
        self.setPixmap(self._render())
        self.repaint()

    # ------------------------------------------------------------------
    def _render(self) -> QPixmap:
        colors = theme.palette()
        pixmap = QPixmap(self.WIDTH, self.HEIGHT)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width, height = self.WIDTH, self.HEIGHT

        # Карточка
        painter.setPen(QPen(QColor(colors["BORDER"]), 1))
        painter.setBrush(QColor(colors["BG"]))
        painter.drawRoundedRect(QRectF(1.5, 1.5, width - 3, height - 3), 16, 16)

        # Верхняя линия с бегущим акцентом
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors["BORDER"]))
        painter.drawRect(QRectF(1.5, 1.5, width - 3, 2))
        segment = 100.0
        position = (math.sin(self._phase) * 0.5 + 0.5) * (width - segment)
        painter.setBrush(QColor(colors["ACCENT"]))
        painter.drawRect(QRectF(position, 1.5, segment, 2))

        # Логотип-луна
        self._draw_moon(painter, QRectF(48, 62, 84, 84), colors["ACCENT"])

        # Заголовок и подзаголовок
        title_font = QFont("Segoe UI", 22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(colors["ACCENT"]))
        painter.drawText(
            QRectF(152, 60, width - 200, 36),
            Qt.AlignLeft | Qt.AlignVCenter,
            APP_DISPLAY_NAME.upper(),
        )

        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor(colors["TEXT_DIM"]))
        painter.drawText(
            QRectF(154, 96, width - 200, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            "характеристики · оптимизация Windows",
        )

        # Прогресс
        track = QRectF(48, 214, width - 96, 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(colors["BORDER"]))
        painter.drawRoundedRect(track, 3, 3)
        filled = track.width() * (self._progress / 100.0)
        if filled > 0:
            painter.setBrush(QColor(colors["ACCENT"]))
            painter.drawRoundedRect(
                QRectF(track.left(), track.top(), max(filled, 5), track.height()), 3, 3
            )
            pulse = 4 + 2 * (math.sin(self._phase * 2) * 0.5 + 0.5)
            painter.setBrush(QColor(colors["ACCENT"]))
            painter.drawEllipse(
                QRectF(
                    track.left() + filled - pulse,
                    track.center().y() - pulse,
                    pulse * 2,
                    pulse * 2,
                )
            )

        # Статус и версия
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(colors["TEXT_DIM"]))
        painter.drawText(
            QRectF(48, 232, width - 96, 20), Qt.AlignLeft | Qt.AlignVCenter, self._message
        )
        painter.setPen(QColor(colors["TEXT_FAINT"]))
        painter.drawText(
            QRectF(48, 268, width - 96, 20),
            Qt.AlignRight | Qt.AlignVCenter,
            f"v{APP_VERSION}",
        )

        painter.end()
        return pixmap

    @staticmethod
    def _draw_moon(painter: QPainter, rect: QRectF, color: str) -> None:
        full = QPainterPath()
        full.addEllipse(rect)
        cut = QPainterPath()
        radius = rect.width()
        cut.addEllipse(rect.translated(radius * 0.42, -radius * 0.42))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(full.subtracted(cut))
