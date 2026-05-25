from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QClipboard, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..service import BotService


class MainWindow(QMainWindow):
    def __init__(self, service: BotService) -> None:
        super().__init__()
        self._service = service
        self.setWindowTitle("GodTierBot")
        self.setMinimumWidth(520)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout()
        root.setLayout(layout)

        self._status = QLabel()
        self._status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._status)

        url = f"http://{service.settings.host}:{service.settings.port}"
        self._url_label = QLabel(url)
        self._url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._url_label)

        btns = QHBoxLayout()
        layout.addLayout(btns)

        self._open_dashboard = QPushButton("Open Dashboard")
        self._copy_url = QPushButton("Copy URL")
        self._pause = QPushButton("Pause")
        self._resume = QPushButton("Resume")
        btns.addWidget(self._open_dashboard)
        btns.addWidget(self._copy_url)
        btns.addWidget(self._pause)
        btns.addWidget(self._resume)

        self._open_dashboard.clicked.connect(self._on_open_dashboard)
        self._copy_url.clicked.connect(self._on_copy_url)
        self._pause.clicked.connect(self._on_pause)
        self._resume.clicked.connect(self._on_resume)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        self._refresh()

    def _on_open_dashboard(self) -> None:
        url = f"http://{self._service.settings.host}:{self._service.settings.port}"
        QDesktopServices.openUrl(QUrl(url))

    def _on_copy_url(self) -> None:
        url = f"http://{self._service.settings.host}:{self._service.settings.port}"
        QApplication.clipboard().setText(url, mode=QClipboard.Clipboard)

    def _on_pause(self) -> None:
        self._service.pause_trading()
        self._refresh()

    def _on_resume(self) -> None:
        self._service.resume_trading()
        self._refresh()

    def _refresh(self) -> None:
        s = self._service.settings
        u = self._service.ui
        lines = [
            f"Mode: {'PAPER' if s.paper_mode else 'LIVE'}",
            f"Trading: {'PAUSED' if u.trading_paused else 'ACTIVE'}",
            f"MT5 Connected: {'YES' if u.mt5_connected else 'NO'}",
        ]
        if u.mt5_last_account:
            lines.append(f"MT5 Account: {u.mt5_last_account}")
        self._status.setText("\n".join(lines))
