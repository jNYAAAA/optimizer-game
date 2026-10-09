"""Фоновое выполнение задач через ``QThreadPool``."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    """Запускает ``fn`` в фоне, транслируя результат через сигналы.

    При ``pass_progress=True`` функция получает keyword-аргумент ``progress`` —
    колбэк ``progress(percent, message)``.
    """

    def __init__(self, fn: Callable, *args: Any, pass_progress: bool = False, **kwargs: Any) -> None:
        super().__init__()
        # Не позволяем пулу удалить объект: владение остаётся у Python, иначе
        # объект-источник сигналов может быть удалён до доставки ``finished``.
        self.setAutoDelete(False)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.pass_progress = pass_progress
        self.signals = WorkerSignals()

    def _emit(self, percent: int, message: str = "") -> None:
        self.signals.progress.emit(int(percent), str(message))

    def run(self) -> None:
        try:
            if self.pass_progress:
                result = self.fn(*self.args, progress=self._emit, **self.kwargs)
            else:
                result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - сообщаем в UI
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


# Пока задача выполняется (и пока не доставлены её сигналы) держим ссылку,
# чтобы сборщик мусора не уничтожил объект раньше времени.
_ACTIVE_WORKERS: set[Worker] = set()


def start_worker(worker: Worker) -> None:
    """Запускает задачу, удерживая ссылку до получения результата."""
    _ACTIVE_WORKERS.add(worker)

    def _release(*_args: Any) -> None:
        _ACTIVE_WORKERS.discard(worker)

    worker.signals.finished.connect(_release)
    worker.signals.failed.connect(_release)
    QThreadPool.globalInstance().start(worker)
