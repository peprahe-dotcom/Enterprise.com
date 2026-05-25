from __future__ import annotations

import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from .bootstrap import load_settings
from .service import BotService
from .server import ApiServer
from .settings import UiState
from .storage import SqliteStore
from .ui.main_window import MainWindow
from .ui.tray import Tray


def main() -> int:
    boot = load_settings()
    paths = boot.settings.paths()
    SqliteStore(paths.db_path).migrate()

    ui_state = UiState()
    service = BotService(settings=boot.settings, ui=ui_state)

    server = ApiServer(service=service)
    server.start()

    app = QApplication(sys.argv)
    win = MainWindow(service)

    def show_window() -> None:
        win.show()
        win.raise_()
        win.activateWindow()

    def quit_app() -> None:
        server.stop()
        app.quit()

    _tray = Tray(service=service, show_window=show_window, quit_app=quit_app)

    show_window()
    if boot.first_run:
        QDesktopServices.openUrl(QUrl(f"http://{boot.settings.host}:{boot.settings.port}"))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

