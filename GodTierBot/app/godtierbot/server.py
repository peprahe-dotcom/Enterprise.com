from __future__ import annotations

import threading

import uvicorn

from .api import create_app
from .service import BotService


class ApiServer:
    def __init__(self, service: BotService) -> None:
        self._service = service
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    def start(self) -> None:
        app = create_app(self._service)
        config = uvicorn.Config(
            app=app,
            host=self._service.settings.host,
            port=self._service.settings.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config=config)

        def run() -> None:
            if self._server is None:
                return
            self._server.run()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True

