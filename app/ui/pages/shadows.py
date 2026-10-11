"""Вкладка «Убрать тени»: sg.ShadowQuality=4 + защита файла «только чтение».

Приём из гайдов по WARDOGS: значение 4 у игральных теней убирает их полностью,
но игра при выходе может записать своё значение обратно. Поэтому файл
GameUserSettings.ini помечается атрибутом «Только чтение».
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.games import (
    SHADOW_DISABLED_VALUE,
    SHADOW_KEY,
    GameProfile,
    GameSettingsResult,
    ShadowStatus,
    remove_shadows,
    restore_shadows,
    shadow_status,
)
from ...core.workers import Worker, start_worker
from .. import theme
from ..widgets import Card, LogView, make_header

STEPS = (
    "1. Win + R → %LocalAppData%\\Wardogs\\Saved\\Config\\WindowsClient → Enter.\n"
    "2. Открыть GameUserSettings.ini (Блокнотом).\n"
    f"3. Найти строку {SHADOW_KEY}=… и поставить {SHADOW_DISABLED_VALUE}.\n"
    "4. Сохранить файл.\n"
    "5. ПКМ по файлу → Свойства → галочка «Только чтение».\n\n"
    "Кнопка ниже делает все пять шагов сразу."
)


class NoShadowsPage(QWidget):
    def __init__(
        self,
        profile: GameProfile,
        parent: QWidget | None = None,
        show_header: bool = True,
    ) -> None:
        super().__init__(parent)
        self.profile = profile

        root = QVBoxLayout(self)
        root.setSpacing(14)
        if show_header:
            root.setContentsMargins(24, 20, 24, 20)
            root.addWidget(
                make_header(
                    "Убрать тени",
                    f"Тени в {profile.name} отключаются значением {SHADOW_KEY}="
                    f"{SHADOW_DISABLED_VALUE}. Чтобы игра не вернула своё значение, файл "
                    "настроек помечается «Только чтение» — как в инструкции.",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        self.help_label = QLabel("Чтение текущего состояния…")
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        root.addWidget(self.help_label)

        card = Card("Состояние")
        self.value_label = card.add_row("Тени в файле", "—")
        self.protect_label = card.add_row("Защита «Только чтение»", "—")
        self.file_label = card.add_row("Файл", "—")
        root.addWidget(card)

        steps = QLabel(STEPS)
        steps.setObjectName("PageHint")
        steps.setWordWrap(True)
        root.addWidget(steps)

        controls = QHBoxLayout()
        self.remove_btn = QPushButton("УБРАТЬ ТЕНИ")
        self.remove_btn.setObjectName("Primary")
        self.remove_btn.clicked.connect(self._remove)
        controls.addWidget(self.remove_btn)
        self.restore_btn = QPushButton("ВЕРНУТЬ ТЕНИ")
        self.restore_btn.setObjectName("Danger")
        self.restore_btn.clicked.connect(self._restore)
        controls.addWidget(self.restore_btn)
        self.refresh_btn = QPushButton("ОБНОВИТЬ")
        self.refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.warn = QLabel(
            "Пока стоит защита, игра не может сохранять настройки графики. Другие "
            "настройки в разделе «Игра» приложение всё равно применит: на время записи "
            "защита снимается и возвращается обратно."
        )
        self.warn.setObjectName("PageHint")
        self.warn.setWordWrap(True)
        root.addWidget(self.warn)

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
        self.refresh_btn.setEnabled(False)
        worker = Worker(shadow_status, self.profile)
        worker.signals.finished.connect(self._on_status)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_status(self, status: ShadowStatus) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.refresh_btn.setEnabled(True)
        palette = theme.palette()

        if not status.ok:
            self.value_label.setText("—")
            self.protect_label.setText("—")
            self.file_label.setText("—")
            self.remove_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            self._status(status.message, palette["DANGER"])
            return

        self.remove_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        self.file_label.setText(status.files[0] if status.files else "—")

        if status.value == SHADOW_DISABLED_VALUE:
            self.value_label.setText(f"{SHADOW_KEY}={status.value} — тени убраны")
            value_color = "OK"
        elif status.value:
            self.value_label.setText(f"{SHADOW_KEY}={status.value} — тени включены")
            value_color = "TEXT_DIM"
        else:
            self.value_label.setText(f"строки {SHADOW_KEY} нет в файле")
            value_color = "WARN"
        self.value_label.setStyleSheet(f"color: {palette[value_color]};")

        if status.readonly:
            self.protect_label.setText("включена — игра не сбросит настройку")
            self.protect_label.setStyleSheet(f"color: {palette['OK']};")
        else:
            self.protect_label.setText("выключена — игра может вернуть свои тени")
            self.protect_label.setStyleSheet(f"color: {palette['WARN']};")

        self._status("Готово. Проверьте значения и нажмите «Убрать тени».", palette["TEXT_DIM"])

    def _status(self, text: str, color: str) -> None:
        self.help_label.setText(text)
        self.help_label.setStyleSheet("" if color == theme.palette()["TEXT_DIM"] else f"color: {color};")

    # ------------------------------------------------------------------
    def _remove(self) -> None:
        self._run("Убираю тени…", remove_shadows)

    def _restore(self) -> None:
        answer = QMessageBox.question(
            self,
            "Вернуть тени",
            "Снять защиту «Только чтение» и вернуть исходные настройки из резервной копии?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run("Возврат настроек…", restore_shadows)

    def _run(self, label: str, fn) -> None:
        self._set_busy(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._status(label, theme.palette()["TEXT_DIM"])
        worker = Worker(fn, self.profile, pass_progress=True)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _set_busy(self, busy: bool) -> None:
        for button in (self.remove_btn, self.restore_btn, self.refresh_btn):
            button.setEnabled(not busy)

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self._status(message, theme.palette()["TEXT_DIM"])

    def _on_done(self, result: GameSettingsResult) -> None:
        self._set_busy(False)
        self.progress.setValue(100)
        color = theme.palette()["OK"] if result.ok else theme.palette()["DANGER"]
        self._status(result.message, color)
        self.log.log(result.message)
        self.refresh()

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._status(f"Ошибка: {message}", theme.palette()["DANGER"])
        self.log.log(f"Ошибка: {message}")
