from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EconomicCalendar:
    def refresh(self) -> None:
        return

    def is_high_impact_window(self, minutes_buffer: int) -> bool:
        return False

