"""Страница драйверов: версии, Windows Update, сайты производителей, плата."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.drivers import (
    DriverInfo,
    MotherboardDriverInfo,
    ProblemDevice,
    VendorDriverInfo,
    check_driver_updates,
    check_gpu_drivers,
    install_nvidia_driver,
    install_windows_driver_updates,
    list_drivers,
    motherboard_driver_info,
    problem_devices,
)
from ...core.workers import Worker, start_worker
from .. import theme
from ..widgets import Card, LogView, make_header


class DriversPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(
            make_header(
                "Драйверы",
                "Версии драйверов, проверка Windows Update и официальных сайтов. "
                "Для материнской платы определяется модель, список нужных драйверов и ссылка "
                "на страницу загрузки у производителя.",
            )
        )

        self.mobo_card = Card("Материнская плата")
        self.mobo_card.add_row("Статус", "Определение платы…")
        self.mobo_btn = QPushButton("СТРАНИЦА ДРАЙВЕРОВ")
        self.mobo_btn.setObjectName("Primary")
        self.mobo_btn.clicked.connect(self._open_mobo)
        self.mobo_btn.setEnabled(False)
        self.mobo_card.add_header_widget(self.mobo_btn)
        self.mobo_search_btn = QPushButton("ПОИСК В БРАУЗЕРЕ")
        self.mobo_search_btn.clicked.connect(self._open_mobo_search)
        self.mobo_search_btn.setEnabled(False)
        self.mobo_card.add_header_widget(self.mobo_search_btn)
        root.addWidget(self.mobo_card)

        self.gpu_card = Card("Видеодрайвер")
        self.gpu_card.add_row("Статус", "Чтение драйверов…")
        root.addWidget(self.gpu_card)

        self.vendor_card = Card("Обновления с сайтов производителей")
        self.vendor_card.add_row("Статус", "Нажмите «Проверить обновления».")
        root.addWidget(self.vendor_card)

        install_row = QHBoxLayout()
        self.install_btn = QPushButton("СКАЧАТЬ И УСТАНОВИТЬ (NVIDIA)")
        self.install_btn.setObjectName("Primary")
        self.install_btn.clicked.connect(self._install_nvidia)
        self.install_btn.hide()
        install_row.addWidget(self.install_btn)
        self.wu_install_btn = QPushButton("УСТАНОВИТЬ ОБНОВЛЕНИЯ WINDOWS")
        self.wu_install_btn.setObjectName("Primary")
        self.wu_install_btn.clicked.connect(self._install_windows)
        self.wu_install_btn.hide()
        install_row.addWidget(self.wu_install_btn)
        install_row.addStretch(1)
        root.addLayout(install_row)

        controls = QHBoxLayout()
        self.check_btn = QPushButton("ПРОВЕРИТЬ ОБНОВЛЕНИЯ")
        self.check_btn.setObjectName("Primary")
        self.check_btn.clicked.connect(self._check)
        controls.addWidget(self.check_btn)
        self.status = QLabel("Проверка ещё не выполнялась.")
        self.status.setObjectName("PageHint")
        self.status.setWordWrap(True)
        controls.addWidget(self.status, 1)
        root.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.problems_card = Card("Не хватает драйверов")
        self.problems_card.add_row("Статус", "Проверка устройств…")
        root.addWidget(self.problems_card)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Устройство", "Класс", "Версия", "Дата", "Поставщик"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        root.addWidget(self.table)

        self.log = LogView()
        self.log.setMaximumHeight(120)
        root.addWidget(self.log)

        self._displays: list[DriverInfo] = []
        self._nvidia_info: VendorDriverInfo | None = None
        self._mobo_url = ""
        self._mobo_search_url = ""
        self._wu_available = False
        self._loaded = False

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.load()

    def load(self) -> None:
        self.progress.setRange(0, 0)

        def task(progress):
            progress(10, "Чтение драйверов…")
            drivers = list_drivers()
            progress(60, "Определение материнской платы…")
            mobo = motherboard_driver_info(drivers)
            progress(80, "Поиск устройств без драйверов…")
            problems = problem_devices()
            return drivers, mobo, problems

        worker = Worker(task, pass_progress=True)
        worker.signals.progress.connect(lambda _p, m: self.status.setText(m))
        worker.signals.finished.connect(self._on_data)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_data(self, result) -> None:
        drivers, mobo, problems = result
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText("Данные обновлены.")

        self._on_mobo(mobo)
        self._on_problems(problems)

        self._displays = [d for d in drivers if d.device_class.upper() == "DISPLAY"]
        self.gpu_card.clear()
        if self._displays:
            for driver in self._displays:
                self.gpu_card.add_row(driver.name, f"{driver.version} · {driver.date}")
        else:
            self.gpu_card.add_row("Видеодрайвер", "Не найден")

        self.table.setRowCount(0)
        for driver in drivers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(driver.name))
            self.table.setItem(row, 1, QTableWidgetItem(driver.class_label))
            self.table.setItem(row, 2, QTableWidgetItem(driver.version))
            self.table.setItem(row, 3, QTableWidgetItem(driver.date))
            self.table.setItem(row, 4, QTableWidgetItem(driver.manufacturer))
        self.log.log(f"Найдено драйверов: {len(drivers)}")

    def _on_mobo(self, mobo: MotherboardDriverInfo) -> None:
        self._mobo_url = mobo.url
        self._mobo_search_url = mobo.search_url
        self.mobo_card.clear()
        self.mobo_card.add_row("Производитель", mobo.manufacturer)
        self.mobo_card.add_row("Модель", mobo.product)
        if mobo.platform:
            self.mobo_card.add_row("Платформа", mobo.platform)
        if mobo.hints:
            self.mobo_card.add_row("Что скачать", " · ".join(mobo.hints))
            self.log.log("Драйверы платы: " + ", ".join(mobo.hints))
        if mobo.url:
            label = self.mobo_card.add_row(
                "Драйверы",
                f'<a href="{mobo.url}">страница драйверов на сайте производителя</a>',
            )
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.mobo_btn.setEnabled(bool(mobo.url))
        self.mobo_search_btn.setEnabled(bool(mobo.search_url))

    def _on_problems(self, problems: list[ProblemDevice]) -> None:
        self.problems_card.clear()
        if not problems:
            self.problems_card.add_row(
                "Статус", "Все устройства работают — драйверов не хватает? Нет."
            )
            return
        self.problems_card.add_row("Найдено устройств", str(len(problems)))
        for device in problems:
            text = f"{device.status} · {device.device_class}"
            label = self.problems_card.add_row(device.name, text)
            links = [f'<a href="{device.search_url}">поиск в браузере</a>']
            if device.hardware_id:
                links.append(f'<a href="{device.catalog_url}">каталог Microsoft</a>')
            label.setText(f"{text} · " + " · ".join(links))
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)

    def _open_mobo(self) -> None:
        if self._mobo_url:
            webbrowser.open(self._mobo_url)

    def _open_mobo_search(self) -> None:
        if self._mobo_search_url:
            webbrowser.open(self._mobo_search_url)

    # ------------------------------------------------------------------
    def _check(self) -> None:
        self.check_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.status.setText("Проверка Windows Update и сайтов производителей…")
        displays = self._displays

        def task(progress):
            progress(5, "Запрос к Windows Update…")
            windows_update = check_driver_updates()
            progress(55, "Проверка сайтов производителей…")
            vendors = check_gpu_drivers(displays)
            return windows_update, vendors

        worker = Worker(task, pass_progress=True)
        worker.signals.progress.connect(lambda _p, m: self.status.setText(m))
        worker.signals.finished.connect(self._on_results)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_results(self, result) -> None:
        windows_update, vendors = result
        self.check_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        palette = theme.palette()

        any_update = False
        self.vendor_card.clear()
        if not vendors:
            self.vendor_card.add_row("Видеодрайверы", "Не найдены")
        for info in vendors:
            any_update = self._add_vendor_row(info, palette) or any_update

        if windows_update.updates:
            any_update = True
            for update in windows_update.updates:
                self.log.log(f"Windows Update: {update.title} ({update.provider})".strip())
        self.log.log(windows_update.message)

        self._nvidia_info = next(
            (i for i in vendors if i.update_available and i.download_url), None
        )
        self.install_btn.setVisible(self._nvidia_info is not None)
        self._wu_available = bool(windows_update.updates)
        self.wu_install_btn.setVisible(self._wu_available)

        if any_update:
            self.status.setText(
                "Есть доступные обновления — нажмите «Скачать и установить»."
            )
            self.status.setStyleSheet(f"color: {palette['WARN']};")
        else:
            self.status.setText("Доступных обновлений не найдено — версии актуальны.")
            self.status.setStyleSheet(f"color: {palette['OK']};")

    def _add_vendor_row(self, info: VendorDriverInfo, palette: dict) -> bool:
        caption = info.device
        if info.latest and info.latest != "—":
            text = f"{info.installed} → {info.latest}"
            if info.release_date:
                text += f" · {info.release_date}"
            if info.update_available:
                text += " · ДОСТУПНО ОБНОВЛЕНИЕ"
            elif info.note:
                text += f" · {info.note}"
        else:
            text = info.installed
            if info.note:
                text += f" · {info.note}"

        label = self.vendor_card.add_row(caption, text)
        if info.url:
            label.setText(f"{text} · <a href=\"{info.url}\">сайт</a>")
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        if info.update_available:
            label.setStyleSheet(f"color: {palette['WARN']};")
            self.log.log(f"{info.device}: доступна версия {info.latest} (установлена {info.installed})")
        elif info.latest and info.latest != "—":
            label.setStyleSheet(f"color: {palette['OK']};")
            self.log.log(f"{info.device}: установлена последняя версия {info.installed}")
        else:
            self.log.log(f"{info.device}: {info.note or 'нет данных об обновлениях'}")
        return info.update_available

    # ------------------------------------------------------------------
    def _install_nvidia(self) -> None:
        info = self._nvidia_info
        if info is None:
            return
        answer = QMessageBox.question(
            self,
            "Установка драйвера NVIDIA",
            f"Скачать и установить драйвер {info.latest} для {info.device}?\n\n"
            "Файл около 1 ГБ; установка может занять несколько минут и потребовать "
            "перезагрузку.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_install(
            "Загрузка драйвера NVIDIA…", install_nvidia_driver, info.download_url
        )

    def _install_windows(self) -> None:
        if not self._wu_available:
            return
        answer = QMessageBox.question(
            self,
            "Установка обновлений Windows",
            "Скачать и установить доступные обновления драйверов через Windows Update?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_install("Установка обновлений Windows…", install_windows_driver_updates)

    def _run_install(self, label: str, fn, *args) -> None:
        self.check_btn.setEnabled(False)
        self.install_btn.setEnabled(False)
        self.wu_install_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(label)
        self.status.setStyleSheet("")
        worker = Worker(fn, *args, pass_progress=True)
        worker.signals.progress.connect(self._on_install_progress)
        worker.signals.finished.connect(self._on_install_done)
        worker.signals.failed.connect(self._on_failed)
        start_worker(worker)

    def _on_install_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        if message:
            self.status.setText(message)

    def _on_install_done(self, result) -> None:
        ok, message = result if isinstance(result, tuple) else (bool(result), "")
        self.check_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        self.wu_install_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        palette = theme.palette()
        self.status.setText(message)
        self.status.setStyleSheet(f"color: {palette['OK'] if ok else palette['DANGER']};")
        self.log.log(message)
        self.load()

    def _on_failed(self, message: str) -> None:
        self.check_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        self.wu_install_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(f"Ошибка: {message}")
        self.status.setStyleSheet(f"color: {theme.palette()['DANGER']};")
        self.log.log(f"Ошибка: {message}")
