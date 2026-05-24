from __future__ import annotations

import importlib
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from advanced_researcher import compute_confluence, detect_setups, enrich_indicators, mark_news_window


DAILY_LOSS_LIMIT_PCT: float = 0.5
BLOCK_IF_ANY_LOW_PROBABILITY: bool = True
POLL_SECONDS: int = 60
SYMBOLS: list[str] = ["EURUSD", "XAUUSD", "BTCUSD", "US30"]
MAGIC: int = 26052401
DEVIATION_POINTS: int = 30


try:
    mt5 = importlib.import_module("MetaTrader5")
except Exception:
    mt5 = None


@dataclass(frozen=True)
class RuntimeRules:
    per_trade_equity_fraction: float
    max_positions_total: int
    block_all_trading: bool
    reason: str
    news_freeze_until_utc: str | None


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _require_mt5() -> Any:
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 Python package is not importable. This script must run on a Windows machine with "
            "MetaTrader 5 terminal installed and the official MetaTrader5 Python package available."
        )
    return mt5


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return json.loads(raw)


def _atomic_write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _load_rules(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    if isinstance(raw, dict):
        return raw
    return {
        "generated_at": _now().isoformat(),
        "global": {"block_all_trading": True, "reason": "ai_live_rules.json missing", "max_positions_total": 1},
        "risk": {"per_trade_equity_fraction": 0.10},
        "symbols": {},
        "meta": {},
    }


def _validate_daily_loss_limit(pct: float) -> float:
    allowed = {0.25, 0.5, 1.0, 2.0, 3.0}
    if pct not in allowed:
        raise ValueError(f"DAILY_LOSS_LIMIT_PCT must be one of {sorted(allowed)}")
    return pct


def _resolve_symbol(requested: str) -> str:
    m = _require_mt5()
    if m.symbol_info(requested) is not None:
        return requested
    cands = m.symbols_get(f"*{requested}*")
    if cands:
        return cands[0].name
    raise RuntimeError(f"Symbol not found on broker: {requested}")


def connect_mt5() -> None:
    m = _require_mt5()
    if not m.initialize():
        raise RuntimeError(f"MT5 initialize failed: {m.last_error()}")


def _account_snapshot() -> dict[str, float]:
    m = _require_mt5()
    ai = m.account_info()
    if ai is None:
        raise RuntimeError(f"account_info failed: {m.last_error()}")
    return {
        "balance": float(ai.balance),
        "equity": float(ai.equity),
        "margin_free": float(ai.margin_free),
    }


def _state_path() -> Path:
    return Path("state_memory.json")


def _load_state() -> dict[str, Any]:
    state = _read_json(_state_path())
    return state if isinstance(state, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    _atomic_write_json(_state_path(), state)


def _get_day_key(ts: datetime) -> str:
    return ts.astimezone(UTC).date().isoformat()


def _ensure_daily_state(equity: float) -> dict[str, Any]:
    now = _now()
    day_key = _get_day_key(now)
    state = _load_state()
    if state.get("day") != day_key:
        state = {"day": day_key, "day_start_equity": float(equity), "halted": False}
        _save_state(state)
        return state
    if "day_start_equity" not in state or not isinstance(state.get("day_start_equity"), (int, float)):
        state["day_start_equity"] = float(equity)
        _save_state(state)
    return state


def _daily_loss_hit(day_start_equity: float, equity: float, pct_limit: float) -> bool:
    if day_start_equity <= 0:
        return False
    dd = (equity - day_start_equity) / day_start_equity
    return dd <= -(pct_limit / 100.0)


def _close_all_positions() -> None:
    m = _require_mt5()
    positions = m.positions_get()
    if positions is None:
        return
    for p in positions:
        sym = str(p.symbol)
        vol = float(p.volume)
        typ = int(p.type)
        tick = m.symbol_info_tick(sym)
        if tick is None:
            continue
        if typ == m.POSITION_TYPE_BUY:
            order_type = m.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            order_type = m.ORDER_TYPE_BUY
            price = float(tick.ask)
        request = {
            "action": m.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": vol,
            "type": order_type,
            "position": int(p.ticket),
            "price": price,
            "deviation": int(DEVIATION_POINTS),
            "magic": int(MAGIC),
            "comment": "daily_drawdown_close",
        }
        m.order_send(request)


def _timeframe(name: Literal["H4", "H1", "M15"]) -> int:
    m = _require_mt5()
    return {"H4": m.TIMEFRAME_H4, "H1": m.TIMEFRAME_H1, "M15": m.TIMEFRAME_M15}[name]


def _fetch_recent_rates(symbol: str, tf: Literal["H4", "H1", "M15"], bars: int) -> pd.DataFrame:
    m = _require_mt5()
    sym = _resolve_symbol(symbol)
    if not m.symbol_select(sym, True):
        raise RuntimeError(f"symbol_select failed for {sym}: {m.last_error()}")
    rates = m.copy_rates_from_pos(sym, _timeframe(tf), 0, int(bars))
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No rates returned for {sym} {tf}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.set_index("time").sort_index()


def _get_spread_points(symbol: str) -> int:
    m = _require_mt5()
    info = m.symbol_info(symbol)
    if info is None:
        return 0
    return int(getattr(info, "spread", 0) or 0)


def _normalize_volume(symbol: str, volume: float) -> float:
    m = _require_mt5()
    info = m.symbol_info(symbol)
    if info is None:
        return 0.0
    vmin = float(info.volume_min)
    vmax = float(info.volume_max)
    step = float(info.volume_step)
    vol = max(vmin, min(vmax, float(volume)))
    if step > 0:
        vol = math.floor(vol / step) * step
    digits = 8
    return float(round(vol, digits))


def _calc_volume_from_equity(symbol: str, equity: float, fraction: float, price: float) -> float:
    m = _require_mt5()
    info = m.symbol_info(symbol)
    if info is None:
        return 0.0
    contract = float(getattr(info, "trade_contract_size", 1.0) or 1.0)
    notional = max(0.0, float(equity) * float(fraction))
    denom = max(1e-12, float(price) * contract)
    vol = notional / denom
    return _normalize_volume(symbol, vol)


def _dom_ok(symbol: str, side: Literal["buy", "sell"]) -> bool:
    m = _require_mt5()
    info = m.symbol_info(symbol)
    if info is None:
        return True
    point = float(getattr(info, "point", 0.0) or 0.0)
    if point <= 0:
        return True
    if hasattr(m, "market_book_add"):
        m.market_book_add(symbol)
    book = m.market_book_get(symbol) if hasattr(m, "market_book_get") else None
    if book is None:
        return True
    try:
        entries = [dict(x._asdict()) for x in book]
    except Exception:
        try:
            entries = [dict(x) for x in book]
        except Exception:
            return True
    tick = m.symbol_info_tick(symbol)
    if tick is None:
        return True
    mid = (float(tick.bid) + float(tick.ask)) / 2.0
    rng = 10.0 * point
    bid_vol = 0.0
    ask_vol = 0.0
    for e in entries:
        price = e.get("price")
        volume = e.get("volume")
        typ = e.get("type")
        if price is None or volume is None or typ is None:
            continue
        try:
            p = float(price)
            v = float(volume)
            t = int(typ)
        except Exception:
            continue
        if abs(p - mid) > rng:
            continue
        if t == getattr(m, "BOOK_TYPE_BUY", 1):
            bid_vol += v
        elif t == getattr(m, "BOOK_TYPE_SELL", 2):
            ask_vol += v
    if (bid_vol + ask_vol) <= 0:
        return True
    if side == "buy":
        return bid_vol >= (ask_vol * 1.15)
    return ask_vol >= (bid_vol * 1.15)


def _build_runtime_rules(raw: dict[str, Any]) -> RuntimeRules:
    g = raw.get("global") if isinstance(raw.get("global"), dict) else {}
    r = raw.get("risk") if isinstance(raw.get("risk"), dict) else {}
    per_trade = float(r.get("per_trade_equity_fraction", 0.10) or 0.10)
    per_trade = float(np.clip(per_trade, 0.0, 0.10))
    max_pos = int(g.get("max_positions_total", 1) or 1)
    max_pos = max(0, min(max_pos, 100))
    block_all = bool(g.get("block_all_trading", False))
    reason = str(g.get("reason", "") or "")
    freeze = g.get("news_freeze_until_utc")
    freeze_s = str(freeze) if isinstance(freeze, str) and freeze else None
    return RuntimeRules(
        per_trade_equity_fraction=per_trade,
        max_positions_total=max_pos,
        block_all_trading=block_all,
        reason=reason,
        news_freeze_until_utc=freeze_s,
    )


def _symbol_rule(raw: dict[str, Any], symbol: str) -> dict[str, Any]:
    s = raw.get("symbols") if isinstance(raw.get("symbols"), dict) else {}
    v = s.get(symbol) if isinstance(s.get(symbol), dict) else {}
    return v


def _symbol_allowed(raw_rules: dict[str, Any], symbol: str, now: datetime) -> tuple[bool, str]:
    v = _symbol_rule(raw_rules, symbol)
    if not bool(v.get("allow_trade", True)):
        return False, "allow_trade=false"
    if bool(v.get("low_probability", False)):
        return False, "low_probability=true"
    blocked = v.get("blocked_hours_utc", [])
    hours = set()
    if isinstance(blocked, list):
        for x in blocked:
            if isinstance(x, (int, float)) and 0 <= int(x) <= 23:
                hours.add(int(x))
    if now.astimezone(UTC).hour in hours:
        return False, "blocked_hour"
    max_spread = int(v.get("max_spread_points", 50) or 50)
    if _get_spread_points(symbol) > max_spread:
        return False, "spread_too_wide"
    return True, "ok"


def _ai_global_blocks(raw_rules: dict[str, Any]) -> tuple[bool, str]:
    rr = _build_runtime_rules(raw_rules)
    if rr.block_all_trading:
        return True, rr.reason or "block_all_trading"
    if rr.news_freeze_until_utc:
        try:
            until = datetime.fromisoformat(rr.news_freeze_until_utc.replace("Z", "+00:00")).astimezone(UTC)
            if _now() <= until:
                return True, "news_freeze"
        except Exception:
            return True, "news_freeze_parse_error"
    if BLOCK_IF_ANY_LOW_PROBABILITY:
        s = raw_rules.get("symbols") if isinstance(raw_rules.get("symbols"), dict) else {}
        for v in s.values():
            if isinstance(v, dict) and bool(v.get("low_probability", False)):
                return True, "low_probability_present"
    return False, "ok"


def _positions_total() -> int:
    m = _require_mt5()
    n = m.positions_total()
    return int(n or 0)


def _send_order(
    symbol: str,
    side: Literal["buy", "sell"],
    volume: float,
    sl: float,
    tp: float,
) -> dict[str, Any] | None:
    m = _require_mt5()
    tick = m.symbol_info_tick(symbol)
    if tick is None:
        return None
    if side == "buy":
        order_type = m.ORDER_TYPE_BUY
        price = float(tick.ask)
    else:
        order_type = m.ORDER_TYPE_SELL
        price = float(tick.bid)
    request = {
        "action": m.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": int(order_type),
        "price": float(price),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": int(DEVIATION_POINTS),
        "magic": int(MAGIC),
        "type_time": int(getattr(m, "ORDER_TIME_GTC", 0)),
    }
    fill_modes = []
    info = m.symbol_info(symbol)
    fm = int(getattr(info, "filling_mode", 0) or 0) if info is not None else 0
    if fm:
        fill_modes.append(fm)
    for candidate in (getattr(m, "ORDER_FILLING_FOK", 0), getattr(m, "ORDER_FILLING_IOC", 1), getattr(m, "ORDER_FILLING_RETURN", 2)):
        if candidate not in fill_modes:
            fill_modes.append(int(candidate))
    for mode in fill_modes:
        request["type_filling"] = int(mode)
        chk = m.order_check(request)
        if chk is None:
            continue
        retcode = int(getattr(chk, "retcode", -1))
        if retcode not in (0, getattr(m, "TRADE_RETCODE_DONE", 10009), getattr(m, "TRADE_RETCODE_PLACED", 10008)):
            continue
        res = m.order_send(request)
        if res is None:
            continue
        return dict(res._asdict()) if hasattr(res, "_asdict") else {"result": str(res)}
    return None


def _trade_db_path() -> Path:
    return Path("live_trade_history.json")


def _init_trade_db() -> None:
    p = _trade_db_path()
    if p.exists():
        return
    _atomic_write_json(p, {"created_at": _now().isoformat(), "trades": [], "deals": []})


def _append_trade_log(entry: dict[str, Any]) -> None:
    _init_trade_db()
    p = _trade_db_path()
    db = _read_json(p)
    if not isinstance(db, dict):
        db = {"created_at": _now().isoformat(), "trades": [], "deals": []}
    trades = db.get("trades")
    if not isinstance(trades, list):
        trades = []
        db["trades"] = trades
    trades.append(entry)
    _atomic_write_json(p, db)


def _append_deals() -> None:
    m = _require_mt5()
    _init_trade_db()
    p = _trade_db_path()
    db = _read_json(p)
    if not isinstance(db, dict):
        return
    existing = db.get("deals")
    if not isinstance(existing, list):
        existing = []
        db["deals"] = existing
    seen = {int(x.get("ticket")) for x in existing if isinstance(x, dict) and isinstance(x.get("ticket"), (int, float))}
    end = _now()
    start = end - timedelta(days=7)
    deals = m.history_deals_get(start, end)
    if deals is None:
        return
    for d in deals:
        try:
            dd = dict(d._asdict())
        except Exception:
            continue
        ticket = dd.get("ticket")
        if ticket is None:
            continue
        try:
            t = int(ticket)
        except Exception:
            continue
        if t in seen:
            continue
        pnl = dd.get("profit")
        try:
            pnl_f = float(pnl) if pnl is not None else None
        except Exception:
            pnl_f = None
        ts = dd.get("time")
        closed_at = None
        if isinstance(ts, (int, float)):
            closed_at = datetime.fromtimestamp(int(ts), tz=UTC).isoformat()
        existing.append(
            {
                "ticket": t,
                "symbol": dd.get("symbol"),
                "type": dd.get("type"),
                "volume": dd.get("volume"),
                "price": dd.get("price"),
                "pnl": pnl_f,
                "closed_at": closed_at,
            }
        )
        seen.add(t)
    _atomic_write_json(p, db)


def _compute_live_news_flags(raw_analysis: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    events = raw_analysis.get("calendar_high_impact")
    if not isinstance(events, list):
        return []
    out = []
    for e in events:
        if not isinstance(e, dict):
            continue
        ts = e.get("time")
        if not isinstance(ts, str):
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            continue
        if abs((t - now).total_seconds()) <= 30 * 60:
            out.append(e)
    return out


def main() -> None:
    _validate_daily_loss_limit(DAILY_LOSS_LIMIT_PCT)
    connect_mt5()
    rules_path = Path("ai_live_rules.json")
    analysis_path = Path("comprehensive_market_analysis.json")
    resolved_symbols: dict[str, str] = {}
    while True:
        loop_start = _now()
        raw_rules = _load_rules(rules_path)
        blocked, block_reason = _ai_global_blocks(raw_rules)
        snap = _account_snapshot()
        state = _ensure_daily_state(snap["equity"])
        day_start = float(state.get("day_start_equity", snap["equity"]))
        if _daily_loss_hit(day_start, snap["equity"], DAILY_LOSS_LIMIT_PCT):
            state["halted"] = True
            _save_state(state)
            _close_all_positions()
            time.sleep(POLL_SECONDS)
            continue
        if bool(state.get("halted")):
            time.sleep(POLL_SECONDS)
            continue
        if blocked:
            time.sleep(POLL_SECONDS)
            continue
        rr = _build_runtime_rules(raw_rules)
        if rr.max_positions_total > 0 and _positions_total() >= rr.max_positions_total:
            time.sleep(POLL_SECONDS)
            continue
        raw_analysis = _read_json(analysis_path)
        if not isinstance(raw_analysis, dict):
            raw_analysis = {}
        near_events = _compute_live_news_flags(raw_analysis, loop_start)
        if near_events:
            time.sleep(POLL_SECONDS)
            continue
        _append_deals()
        for sym in SYMBOLS:
            try:
                resolved = resolved_symbols.get(sym)
                if not resolved:
                    resolved = _resolve_symbol(sym)
                    resolved_symbols[sym] = resolved
                allowed, why = _symbol_allowed(raw_rules, sym, loop_start)
                if not allowed:
                    continue
                h4 = enrich_indicators(_fetch_recent_rates(sym, "H4", 400))
                h1 = enrich_indicators(_fetch_recent_rates(sym, "H1", 600))
                m15 = enrich_indicators(_fetch_recent_rates(sym, "M15", 800))
                m15["confluence_score"] = compute_confluence(h4, h1, m15)
                m15["near_high_impact_news"] = mark_news_window(m15.index, raw_analysis.get("calendar_high_impact") if isinstance(raw_analysis.get("calendar_high_impact"), list) else [])
                setup = detect_setups(sym, m15)
                if len(setup) == 0:
                    continue
                last_row = setup.iloc[-2]
                if not bool(last_row.get("is_sniper", False)):
                    continue
                side = str(last_row.get("setup_side") or "")
                if side not in ("buy", "sell"):
                    continue
                side_l = cast(Literal["buy", "sell"], side)
                if not _dom_ok(resolved, side_l):
                    continue
                entry_row = m15.iloc[-1]
                atr = float(entry_row.get("atr") or 0.0)
                if not math.isfinite(atr) or atr <= 0:
                    continue
                tick = _require_mt5().symbol_info_tick(resolved)
                if tick is None:
                    continue
                price = float(tick.ask) if side == "buy" else float(tick.bid)
                v = _symbol_rule(raw_rules, sym)
                atr_sl_mult = float(v.get("atr_sl_mult", 1.5) or 1.5)
                atr_tp_mult = float(v.get("atr_tp_mult", 3.0) or 3.0)
                if side == "buy":
                    sl = price - atr_sl_mult * atr
                    tp = price + atr_tp_mult * atr
                else:
                    sl = price + atr_sl_mult * atr
                    tp = price - atr_tp_mult * atr
                volume = _calc_volume_from_equity(resolved, snap["equity"], rr.per_trade_equity_fraction, price)
                if volume <= 0:
                    continue
                res = _send_order(resolved, side_l, volume, sl, tp)
                if res:
                    _append_trade_log(
                        {
                            "time": loop_start.isoformat(),
                            "symbol": sym,
                            "resolved_symbol": resolved,
                            "side": side,
                            "volume": volume,
                            "price": price,
                            "sl": sl,
                            "tp": tp,
                            "atr": atr,
                            "rule_reason": why,
                            "order_result": res,
                            "equity": snap["equity"],
                        }
                    )
            except Exception:
                continue
        elapsed = (_now() - loop_start).total_seconds()
        sleep_for = max(1.0, float(POLL_SECONDS) - elapsed)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
