from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade_pct: float = 0.01
    max_daily_loss_pct: float = 0.05
    max_total_drawdown_pct: float = 0.2


def veto_if_not_armed(armed: bool) -> RiskDecision:
    if not armed:
        return RiskDecision(False, "trading_not_armed")
    return RiskDecision(True, "")

