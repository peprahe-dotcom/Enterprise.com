from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Engine:
    paper_mode: bool = True

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

