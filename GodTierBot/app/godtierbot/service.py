from __future__ import annotations

import time
from dataclasses import dataclass

from .settings import Command, Mt5PollRequest, Mt5PollResponse, RuntimeSettings, UiState


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class BotService:
    settings: RuntimeSettings
    ui: UiState

    def pause_trading(self) -> None:
        self.ui.trading_paused = True

    def resume_trading(self) -> None:
        self.ui.trading_paused = False

    def poll_from_mt5(self, req: Mt5PollRequest) -> Mt5PollResponse:
        if self.settings.mt5_shared_token is not None and req.token is not None:
            if req.token != self.settings.mt5_shared_token:
                return Mt5PollResponse(ok=False, commands=[], message="unauthorized")

        self.ui.last_heartbeat_ms = req.timestamp_ms
        self.ui.mt5_connected = True
        self.ui.mt5_last_account = req.account_id

        cmds: list[Command] = []
        if self.ui.trading_paused:
            cmds.append(Command(type="pause", payload={}))
        else:
            cmds.append(Command(type="noop", payload={}))

        return Mt5PollResponse(ok=True, commands=cmds, message="ok")
