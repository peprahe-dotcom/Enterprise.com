from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PostgresLogger:
    def log(self, kind: str, payload: dict) -> None:
        return

