from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..service import BotService


class Tray:
    def __init__(self, service: BotService, show_window: callable, quit_app: callable) -> None:
        self._service = service
        self._show_window = show_window
        self._quit_app = quit_app

        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon())
        self._tray.setToolTip("GodTierBot")

        menu = QMenu()

        open_ui = QAction("Open App")
        open_dash = QAction("Open Dashboard")
        pause = QAction("Pause Trading")
        resume = QAction("Resume Trading")
        quit_action = QAction("Exit")

        open_ui.triggered.connect(self._show_window)
        open_dash.triggered.connect(self._open_dashboard)
        pause.triggered.connect(self._pause)
        resume.triggered.connect(self._resume)
        quit_action.triggered.connect(self._quit_app)

        menu.addAction(open_ui)
        menu.addAction(open_dash)
        menu.addSeparator()
        menu.addAction(pause)
        menu.addAction(resume)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda _: self._show_window())
        self._tray.show()

        self._timer = QTimer()
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_tooltip)
        self._timer.start()

        self._refresh_tooltip()

    def _open_dashboard(self) -> None:
        url = f"http://{self._service.settings.host}:{self._service.settings.port}"
        QDesktopServices.openUrl(QUrl(url))

    def _pause(self) -> None:
        self._service.pause_trading()
        self._refresh_tooltip()

    def _resume(self) -> None:
        self._service.resume_trading()
        self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        u = self._service.ui
        status = "PAUSED" if u.trading_paused else "ACTIVE"
        mt5 = "MT5: YES" if u.mt5_connected else "MT5: NO"
        self._tray.setToolTip(f"GodTierBot | {status} | {mt5}")
