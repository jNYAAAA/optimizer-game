"""Параметры запуска игры (Steam).

Строка параметров хранится в конфигурации Steam, поэтому приложение
показывает её, подставляет рекомендованный набор и записывает обратно
(с резервной копией и возможностью возврата).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
    restore_launch_options,
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

        root = QVBoxLayout(self)
        root.setSpacing(14)
        if show_header:
            root.setContentsMargins(24, 20, 24, 20)
            root.addWidget(
                make_header(
                    "Параметры запуска",
                    "Строка параметров запуска игры из Steam. Приложение записывает её "
                    "в конфигурацию Steam напрямую — Steam при этом должен быть закрыт.",
                )
            )
        else:
            root.setContentsMargins(0, 0, 0, 0)

        self.help_label = QLabel(
            "Параметры применяются к Steam-версии игры. Закройте Steam перед записью."
        )
        self.help_label.setObjectName("PageHint")
        self.help_label.setWordWrap(True)
        root.addWidget(self.help_label)

        card = Card("Параметры запуска Steam")
        appid = STEAM_APPIDS.get(game_key)
        self.appid_label = card.add_row("Идентификатор Steam", str(appid) if appid else "—")
        self.file_label = card.add_row("Конфигурация Steam", "Поиск…")
        row = card.body.rowCount()
        caption = QLabel("ПАРАМЕТРЫ")
        caption.setObjectName("Caption")
        card.body.addWidget(caption, row, 0, Qt.AlignTop)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("например: -dx12 -high -nosplash")
        self.edit.setClearButtonEnabled(True)
        card.body.addWidget(self.edit, row, 1)
        if not appid:
            self.edit.setEnabled(False)
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
        self.recommend_btn = QPushButton("РЕКОМЕНДОВАННЫЕ")
        self.recommend_btn.clicked.connect(self._fill_recommended)
        controls.addWidget(self.recommend_btn)
        self.clear_btn = QPushButton("ОЧИСТИТЬ СТРОКУ")
        self.clear_btn.clicked.connect(self._clear)
        controls.addWidget(self.clear_btn)
        self.restore_btn = QPushButton("ВОССТАНОВИТЬ")
        self.restore_btn.setObjectName("Danger")
        self.restore_btn.clicked.connect(self._restore)
        controls.addWidget(self.restore_btn)
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

        self.apply_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        if not appid:
            self.recommend_btn.setEnabled(False)
        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        if self.game_key not in STEAM_APPIDS:
            self.file_label.setText("Для этой игры параметры запуска недоступны.")
            self.log.log("Игра не найдена в Steam (неизвестен идентификатор).")
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
            self.file_label.setText("localconfig.vdf не найден — установлен ли Steam?")
            self.apply_btn.setEnabled(False)
            self.status("Конфигурация Steam не найдена.", palette["DANGER"])
            return

        self.file_label.setText(f'{len(files)}: {files[0]}')
        if value:
            self.edit.setText(value)
        self.apply_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)

        if value is None:
            self.status(
                "Игра ещё не появлялась в конфигурации Steam — запустите её через Steam "
                "хотя бы раз, затем нажмите «Обновить».",
                palette["WARN"],
            )
            self.apply_btn.setEnabled(False)
            return
        note = " Steam запущен — закройте его перед записью." if steam_running() else ""
        self.status(
            f"Найдено файлов конфигурации: {len(files)}.{note}",
            palette["WARN"] if note else palette["TEXT_DIM"],
        )

    def status(self, text: str, color: str) -> None:
        self.help_label.setText(text)
        self.help_label.setStyleSheet(f"color: {color};")
        if color == theme.palette()["TEXT_DIM"]:
            self.help_label.setStyleSheet("")

    # ------------------------------------------------------------------
    def _fill_recommended(self) -> None:
        value = RECOMMENDED.get(self.game_key, "")
        if value:
            self.edit.setText(value)
            self.log.log("Подставлены рекомендованные параметры запуска.")
        else:
            self.log.log("Готовых параметров для этой игры нет — введите строку вручную.")

    def _clear(self) -> None:
        self.edit.clear()
        self.log.log("Строка параметров очищена. Нажмите «Применить», чтобы сохранить.")

    def _restore(self) -> None:
        answer = QMessageBox.question(
            self,
            "Возврат параметров запуска",
            "Вернуть исходные параметры запуска из резервной копии?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run("Возврат параметров запуска…", restore_launch_options, self.game_key)

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
        for button in (self.apply_btn, self.restore_btn, self.refresh_btn, self.recommend_btn):
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
