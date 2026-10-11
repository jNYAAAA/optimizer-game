"""Параметры запуска игры (Steam).

Строка параметров хранится в конфигурации Steam, поэтому приложение
подставляет рекомендованный набор прямо в поле, а остаётся нажать «Применить».
Перед записью делается резервная копия (возврат доступен из API ядра).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.launch_options import (
    RECOMMENDED,
    RECOMMENDED_HELP,
    STEAM_APPIDS,
    LaunchOptionsResult,
    apply_launch_options,
    current_launch_options,
    steam_running,
)
from ...core.workers import Worker, start_worker
from .. import theme
from ..widgets import Card, LogView, make_header


class LaunchOptionsPage(QWidget):
    def __init__(
        self,
        game_key: str = "cs2",
        parent: QWidget | None = None,
        show_header: bool = True,
    ) -> None:
        super().__init__(parent)
        self.game_key = game_key
        self.appid = STEAM_APPIDS.get(game_key)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        if show_header:
            root.setContentsMargins(24, 20, 24, 20)
            root.addWidget(
                make_header(
                    "Параметры запуска",
                    "Строка параметров запуска игры из Steam. Рекомендованные параметры уже "
                    "подставлены — проверьте и нажмите «Применить». Steam должен быть закрыт.",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        self.help_label = QLabel("Чтение настроек Steam…")
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        root.addWidget(self.help_label)

        card = Card("Параметры запуска Steam")
        row = card.body.rowCount()
        caption = QLabel("ПАРАМЕТРЫ")
        caption.setObjectName("Caption")
        card.body.addWidget(caption, row, 0, Qt.AlignTop)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("например: -dx12 -high -nosplash")
        self.edit.setClearButtonEnabled(True)
        card.body.addWidget(self.edit, row, 1)
        root.addWidget(card)

        hint = QLabel(RECOMMENDED_HELP)
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply)
        controls.addWidget(self.apply_btn)
        self.clear_btn = QPushButton("ОЧИСТИТЬ СТРОКУ")
        self.clear_btn.clicked.connect(self._clear)
        controls.addWidget(self.clear_btn)
        self.refresh_btn = QPushButton("ОБНОВИТЬ")
        self.refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        self.log.setMaximumHeight(110)
        root.addWidget(self.log)
        root.addStretch(1)

        if self.appid is None:
            self.edit.setEnabled(False)
            self.apply_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.help_label.setText(
                "Для этой игры неизвестен идентификатор Steam — параметры запуска недоступны."
            )
        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        if self.appid is None:
            return
        self.progress.setRange(0, 0)
        self.refresh_btn.setEnabled(False)
        worker = Worker(current_launch_options, self.game_key)
        worker.signals.finished.connect(self._on_current)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_current(self, result: tuple) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.refresh_btn.setEnabled(True)
        value, files = result
        palette = theme.palette()

        if not files:
            self.apply_btn.setEnabled(False)
            self.status(
                "Конфигурация Steam (localconfig.vdf) не найдена — установлен ли Steam?",
                palette["DANGER"],
            )
            return

        where = f"Файл: {files[0]}" + (f" (всего {len(files)})" if len(files) > 1 else "")
        recommended = RECOMMENDED.get(self.game_key, "")
        running = steam_running()

        if value is None:
            self.apply_btn.setEnabled(False)
            if recommended:
                self.edit.setText(recommended)
            self.status(
                "Игра ещё не появлялась в конфигурации Steam — запустите её через Steam "
                "хотя бы раз, затем нажмите «Обновить».",
                palette["WARN"],
            )
            return

        self.apply_btn.setEnabled(True)
        if recommended:
            # Рекомендованные параметры подставлены сразу — остаётся нажать «Применить».
            self.edit.setText(recommended)
            if value == recommended:
                note = "В Steam уже записаны рекомендованные параметры."
            elif value:
                note = f"Рекомендованные подставлены вместо текущих («{value}»)."
            else:
                note = "Рекомендованные параметры подставлены — нажмите «Применить»."
        elif value:
            self.edit.setText(value)
            note = "Текущие параметры запуска загружены из Steam."
        else:
            note = "Параметры запуска не заданы — впишите строку и нажмите «Применить»."
        if running:
            note += " Steam запущен: закройте его, иначе запись потеряется."
        self.status(f"{note} {where}", palette["WARN"] if running else palette["TEXT_DIM"])

    def status(self, text: str, color: str) -> None:
        self.help_label.setText(text)
        self.help_label.setStyleSheet("" if color == theme.palette()["TEXT_DIM"] else f"color: {color};")

    # ------------------------------------------------------------------
    def _clear(self) -> None:
        self.edit.clear()
        self.log.log("Строка очищена. Нажмите «Применить», чтобы убрать параметры запуска.")

    def _apply(self) -> None:
        value = self.edit.text().strip()
        label = "Запись параметров запуска…" if value else "Очистка параметров запуска…"
        self._run(label, apply_launch_options, self.game_key, value)

    def _run(self, label: str, fn, *args) -> None:
        self._set_busy(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status(label, theme.palette()["TEXT_DIM"])
        worker = Worker(fn, *args, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _set_busy(self, busy: bool) -> None:
        for button in (self.apply_btn, self.clear_btn, self.refresh_btn):
            button.setEnabled(not busy)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status(message, theme.palette()["TEXT_DIM"])

    def _on_done(self, result: LaunchOptionsResult) -> None:
        self._set_busy(False)
        self.progress.setValue(100)
        color = theme.palette()["OK"] if result.ok else theme.palette()["DANGER"]
        self.status(result.message, color)
        self.log.log(result.message)
        self.refresh()

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status(f"Ошибка: {message}", theme.palette()["DANGER"])
        self.log.log(f"Ошибка: {message}")
