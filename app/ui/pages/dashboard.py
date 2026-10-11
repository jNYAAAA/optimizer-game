"""Стартовая страница: характеристики ПК и загрузка в реальном времени."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ...core.hardware import MonitorInfo, SystemInfo, collect_system_info, live_stats
from ...core.sensors import SensorReading, collect_temperatures
from ...core.workers import Worker, start_worker
from ...utils import format_bytes, format_mhz
from .. import theme
from ..widgets import Card, make_header


def _format_uptime(seconds: int) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} д")
    parts.append(f"{hours} ч")
    parts.append(f"{minutes} мин")
    parts.append(f"{secs} с")
    return " ".join(parts)


class _LivePanel(QFrame):
    """Показатели загрузки CPU и RAM, обновляемые по таймеру."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.cpu_label = QLabel("—")
        self.cpu_label.setObjectName("Value")
        self.cpu_label.setFixedWidth(240)
        self.ram_label = QLabel("—")
        self.ram_label.setObjectName("Value")
        self.ram_label.setFixedWidth(240)

        layout.addLayout(self._row("Загрузка процессора", self.cpu_bar, self.cpu_label))
        layout.addLayout(self._row("Использование памяти", self.ram_bar, self.ram_label))

        self.uptime_label = QLabel("—")
        self.uptime_label.setObjectName("Caption")
        layout.addWidget(self.uptime_label)

    @staticmethod
    def _row(caption: str, bar: QProgressBar, value: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(caption.upper())
        label.setObjectName("Caption")
        label.setFixedWidth(170)
        row.addWidget(label)
        row.addWidget(bar, 1)
        row.addWidget(value)
        return row


class DashboardPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        root.addWidget(
            make_header(
                "Характеристики ПК",
                "Данные собраны при запуске. Загрузка процессора и памяти обновляется автоматически.",
            )
        )

        self.live = _LivePanel()
        root.addWidget(self.live)

        self.status = QLabel("Подготовка…")
        self.status.setObjectName("PageHint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.cpu_card = Card("Процессор")
        self.ram_card = Card("Оперативная память")
        self.gpu_card = Card("Видеокарта")
        self.disk_card = Card("Накопители")
        self.os_card = Card("Операционная система")
        self.board_card = Card("Материнская плата и BIOS")
        grid.addWidget(self.cpu_card, 0, 0)
        grid.addWidget(self.ram_card, 0, 1)
        grid.addWidget(self.gpu_card, 1, 0)
        grid.addWidget(self.disk_card, 1, 1)
        grid.addWidget(self.os_card, 2, 0)
        grid.addWidget(self.board_card, 2, 1)
        self.sensors_card = Card("Датчики и температура")
        self.sensors_card.add_row("Статус", "Чтение датчиков…")
        grid.addWidget(self.sensors_card, 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)
        root.addStretch(1)

        live_stats()  # «прогреваем» счётчик CPU, первый вызов всегда 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

        # Датчики опрашиваются реже и только пока страница видима.
        self._sensors_busy = False
        self._sensor_readings: list[SensorReading] = []
        self._sensors_timer = QTimer(self)
        self._sensors_timer.setInterval(6000)
        self._sensors_timer.timeout.connect(self._refresh_sensors)

        self.load()

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._sensors_timer.start()
        self._refresh_sensors()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._sensors_timer.stop()
        super().hideEvent(event)

    def on_theme_changed(self) -> None:
        # Перерисовываем уже прочитанные датчики в новых цветах, не опрашивая их заново.
        if self._sensor_readings:
            self._render_sensors()
        else:
            self._refresh_sensors()

    def load(self) -> None:
        self.status.setText("Сбор данных о системе…")
        worker = Worker(collect_system_info, pass_progress=True)
        worker.signals.progress.connect(lambda _percent, message: self.status.setText(message))
        worker.signals.finished.connect(self._on_info)
        worker.signals.failed.connect(self._on_error)
        start_worker(worker)

    def _on_error(self, message: str) -> None:
        self.status.setText(f"Не удалось собрать данные: {message}")

    def _on_info(self, info: SystemInfo) -> None:
        if info.error:
            self.status.setText(f"Данные собраны в резервном режиме. {info.error}")
        else:
            self.status.setText("Данные о системе обновлены.")

        cpu = info.cpu
        self.cpu_card.clear()
        self.cpu_card.add_row("Модель", cpu.name)
        self.cpu_card.add_row("Ядра / потоки", f"{cpu.cores} / {cpu.threads}")
        self.cpu_card.add_row("Макс. частота", format_mhz(cpu.max_clock_mhz))
        self.cpu_card.add_row("Сокет", cpu.socket)
        self.cpu_card.add_row(
            "Кэш L2 / L3",
            f"{format_bytes(cpu.l2_cache_bytes)} / {format_bytes(cpu.l3_cache_bytes)}",
        )
        self.cpu_card.add_row("Разрядность", f"{cpu.arch}-бит")

        ram = info.ram
        self.ram_card.clear()
        self.ram_card.add_row("Всего", format_bytes(ram.total_bytes))
        self.ram_card.add_row("Модулей", str(len(ram.modules)))
        if ram.modules:
            first = ram.modules[0]
            self.ram_card.add_row("Тип", first.memory_type)
            self.ram_card.add_row(
                "Частота", format_mhz(first.speed_mhz or first.configured_mhz)
            )
            self.ram_card.add_row("Форм-фактор", first.form_factor)
            for index, module in enumerate(ram.modules, 1):
                self.ram_card.add_row(
                    f"Модуль {index}",
                    f"{format_bytes(module.capacity_bytes)} · {module.memory_type} · "
                    f"{module.speed_mhz} МГц · {module.slot}",
                )

        self.gpu_card.clear()
        if info.gpus:
            multiple = len(info.gpus) > 1
            for index, gpu in enumerate(info.gpus, 1):
                prefix = f"{index}. " if multiple else ""
                self.gpu_card.add_row(f"{prefix}Модель", gpu.name)
                self.gpu_card.add_row(
                    f"{prefix}Видеопамять",
                    format_bytes(gpu.vram_bytes) if gpu.vram_bytes else "—",
                )
                self.gpu_card.add_row(
                    f"{prefix}Драйвер", f"{gpu.driver_version} ({gpu.driver_date})"
                )
                if gpu.resolution != "—":
                    self.gpu_card.add_row(
                        f"{prefix}Разрешение", f"{gpu.resolution} @ {gpu.refresh_rate} Гц"
                    )
        else:
            self.gpu_card.add_row("Видеокарта", "Данные недоступны")

        monitors = self._collect_monitors()
        if monitors:
            self.gpu_card.add_row("Мониторов", str(len(monitors)))
            for index, monitor in enumerate(monitors, 1):
                model = monitor.model if monitor.model and monitor.model != "—" else monitor.device
                manufacturer = monitor.manufacturer or ""
                if manufacturer and manufacturer != "—" and manufacturer.lower() not in model.lower():
                    model = f"{manufacturer} {model}"
                label = f"Монитор {index}" + (" · основной" if monitor.primary else "")
                resolution = (
                    f"{monitor.width}×{monitor.height}"
                    if monitor.width and monitor.height
                    else "—"
                )
                refresh = f" @ {monitor.refresh:.0f} Гц" if monitor.refresh else ""
                self.gpu_card.add_row(label, f"{resolution}{refresh} · {model}")

        self.disk_card.clear()
        if info.disks:
            for index, disk in enumerate(info.disks, 1):
                self.disk_card.add_row(
                    f"Диск {index}",
                    f"{disk.friendly_name}\n{format_bytes(disk.size_bytes)} · "
                    f"{disk.media_type} · {disk.bus_type}",
                )
        for partition in info.partitions:
            self.disk_card.add_row(
                partition.mountpoint,
                f"{format_bytes(partition.used)} / {format_bytes(partition.total)} "
                f"({partition.percent:.0f}%) · {partition.fstype}",
            )
        if not info.disks and not info.partitions:
            self.disk_card.add_row("Накопители", "Данные недоступны")

        os_info = info.os_info
        self.os_card.clear()
        self.os_card.add_row("Название", os_info.caption)
        self.os_card.add_row("Версия", f"{os_info.version} (сборка {os_info.build})")
        self.os_card.add_row("Разрядность", os_info.arch)
        self.os_card.add_row("Установлена", os_info.install_date)
        self.os_card.add_row("Компьютер", os_info.computer_name)
        self.os_card.add_row("Пользователь", os_info.user)

        board = info.motherboard
        self.board_card.clear()
        self.board_card.add_row("Плата", f"{board.manufacturer} {board.product}".strip())
        self.board_card.add_row("Версия платы", board.version)
        self.board_card.add_row("BIOS", f"{board.bios_vendor} {board.bios_version}".strip())
        self.board_card.add_row("Дата BIOS", board.bios_date)

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        stats = live_stats()
        cpu = stats["cpu_percent"]
        freq = stats["cpu_freq_current"]
        self.live.cpu_bar.setValue(int(cpu))
        self.live.cpu_label.setText(f"{cpu:.0f}%" + (f" · {freq} МГц" if freq else ""))
        self.live.ram_bar.setValue(int(stats["ram_percent"]))
        self.live.ram_label.setText(
            f"{format_bytes(stats['ram_used'])} / {format_bytes(stats['ram_total'])} "
            f"({stats['ram_percent']:.0f}%)"
        )
        self.live.uptime_label.setText(
            f"ВРЕМЯ РАБОТЫ СИСТЕМЫ: {_format_uptime(stats['uptime_seconds'])}"
        )

    # ------------------------------------------------------------------
    def _refresh_sensors(self) -> None:
        if self._sensors_busy:
            return
        self._sensors_busy = True
        worker = Worker(collect_temperatures)
        worker.signals.finished.connect(self._on_sensors)
        worker.signals.failed.connect(self._on_sensors_failed)
        start_worker(worker)

    def _on_sensors(self, readings: list[SensorReading]) -> None:
        self._sensors_busy = False
        self._sensor_readings = readings
        self._render_sensors()

    def _render_sensors(self) -> None:
        card = self.sensors_card
        card.clear()
        readings = self._sensor_readings
        if not readings:
            card.add_row("Статус", "Датчики не найдены.")
            return
        palette = theme.palette()
        for reading in readings:
            text = (
                f"{reading.value:.0f} RPM"
                if reading.unit == "RPM"
                else f"{reading.value:.0f} °C"
            )
            value_label = card.add_row(reading.name, text)
            value_label.setToolTip(f"{reading.component} · источник: {reading.source}")
            if reading.unit != "RPM":
                if reading.value >= 85:
                    value_label.setStyleSheet(f"color: {palette['DANGER']};")
                elif reading.value >= 70:
                    value_label.setStyleSheet(f"color: {palette['WARN']};")

    def _on_sensors_failed(self, message: str) -> None:
        self._sensors_busy = False
        self._sensor_readings = []
        self.sensors_card.clear()
        self.sensors_card.add_row("Статус", f"Не удалось прочитать датчики: {message}")

    @staticmethod
    def _collect_monitors() -> list[MonitorInfo]:
        """Мониторы через Qt: физическое разрешение, частота, модель."""
        primary_screen = QGuiApplication.primaryScreen()
        primary_name = primary_screen.name() if primary_screen else ""
        monitors: list[MonitorInfo] = []
        for index, screen in enumerate(QGuiApplication.screens(), 1):
            geometry = screen.geometry()
            ratio = screen.devicePixelRatio() or 1.0
            monitors.append(
                MonitorInfo(
                    device=screen.name() or f"Дисплей {index}",
                    model=screen.model() or "—",
                    manufacturer=screen.manufacturer() or "—",
                    width=int(round(geometry.width() * ratio)),
                    height=int(round(geometry.height() * ratio)),
                    refresh=float(screen.refreshRate() or 0.0),
                    primary=bool(screen.name() and screen.name() == primary_name),
                    x=geometry.x(),
                    y=geometry.y(),
                )
            )
        return monitors
