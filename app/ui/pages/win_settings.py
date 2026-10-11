"""Игровые настройки Windows."""
from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.win_settings import WinSetting, win_settings_for
from ...core.workers import Worker, start_worker
from .. import theme
from ..widgets import Card, LogView, OptionRow, make_header


class WinSettingsPage(QWidget):
    def __init__(
        self,
        game_key: str = "cs2",
        parent: QWidget | None = None,
        show_header: bool = True,
    ) -> None:
        super().__init__(parent)
        self.game_key = game_key
        self._settings = win_settings_for(game_key)
        root = QVBoxLayout(self)
        root.setSpacing(14)
        if show_header:
            root.setContentsMargins(24, 20, 24, 20)
            root.addWidget(
                make_header(
                    "Настройки Windows",
                    "Игровые настройки Windows: питание, HAGS, игровой режим и другое. "
                    "Часть параметров требует прав администратора и перезагрузки.",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        card = Card("Параметры")
        self._rows: list[tuple[WinSetting, OptionRow]] = []
        for setting in self._settings:
            row = OptionRow(setting.name, setting.help, setting.options, setting.value)
            row.apply_requested.connect(lambda value, s=setting: self._apply_one(s, value))
            card.body.addWidget(row, card.body.rowCount(), 0, 1, 2)
            self._rows.append((setting, row))
        root.addWidget(card)

        controls = QHBoxLayout()
        self.apply_btn = QPushButton("ПРИМЕНИТЬ ВСЁ")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self._apply_all)
        controls.addWidget(self.apply_btn)
        self.refresh_btn = QPushButton("ОБНОВИТЬ")
        self.refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_btn)
        self.status = QLabel("Чтение текущих значений…")
        self.status.setObjectName("PageHint")
        self.status.setWordWrap(True)
        controls.addWidget(self.status, 1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = LogView()
        self.log.setMaximumHeight(110)
        root.addWidget(self.log)
        root.addStretch(1)

        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        self.progress.setRange(0, 0)

        def task():
            return {setting.key: setting.get() for setting in self._settings}

        worker = Worker(task)
        worker.signals.finished.connect(self._on_states)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_states(self, states: dict) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        labels = {
            setting.key: next(
                (label for value, label in setting.options if value == states.get(setting.key)),
                states.get(setting.key, "—"),
            )
            for setting in self._settings
        }
        for setting in self._settings:
            self.log.log(f"{setting.name}: сейчас — {labels.get(setting.key, '—')}")
        self.status.setText("Рекомендованные значения выбраны. В журнале — текущее состояние.")
        self.status.setStyleSheet(f"color: {theme.palette()['TEXT_DIM']};")

    def _set_busy(self, busy: bool) -> None:
        self.apply_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        for _setting, row in self._rows:
            row.apply_btn.setEnabled(not busy)

    def _apply_all(self) -> None:
        items = [(setting, row.value()) for setting, row in self._rows]
        self._run(items)

    def _apply_one(self, setting: WinSetting, value: str) -> None:
        self._run([(setting, value)])

    def _run(self, items: list) -> None:
        self._set_busy(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        def task(progress):
            results = []
            total = max(len(items), 1)
            for index, (setting, value) in enumerate(items):
                progress(int(index / total * 100), setting.name)
                ok, message = setting.apply(value)
                results.append((setting.name, ok, message))
            return results

        worker = Worker(task, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_done(self, results: list) -> None:
        palette = theme.palette()
        self._set_busy(False)
        self.progress.setValue(100)
        failures = 0
        for name, ok, message in results:
            if ok:
                self.log.log(f"{name}: {message}")
            else:
                failures += 1
                self.log.log(f"{name}: ошибка — {message}")
        self.status.setText("Готово." if not failures else f"С ошибками: {failures}")
        self.status.setStyleSheet(f"color: {palette['OK'] if not failures else palette['DANGER']};")
        self.refresh()

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Ошибка: {message}")
        self.status.setStyleSheet(f"color: {theme.palette()['DANGER']};")
        self.log.log(f"Ошибка: {message}")
