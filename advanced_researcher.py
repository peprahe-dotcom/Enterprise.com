from __future__ import annotations

import json
import importlib
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

try:
    mt5 = importlib.import_module("MetaTrader5")
except Exception:
    mt5 = None


TimeframeName = Literal["H4", "H1", "M15"]


@dataclass(frozen=True)
class BacktestStats:
    trades: int
    net_profit: float
    sharpe: float
    max_drawdown: float


@dataclass(frozen=True)
class SetupEvent:
    symbol: str
    timeframe: TimeframeName
    ts: str
    side: Literal["buy", "sell"]
    close: float
    rsi: float
    bb_upper: float
    bb_lower: float
    atr: float
    macd_hist: float
    obv: float
    confluence_ok: bool
    near_high_impact_news: bool


def _require_mt5() -> Any:
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 Python package is not importable. This script must run on a Windows machine with "
            "MetaTrader 5 terminal installed and the official MetaTrader5 Python package available."
        )
    return mt5


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _safe_float(x: Any) -> float:
    if x is None:
        return float("nan")
    if isinstance(x, (int, float, np.floating)):
        return float(x)
    return float(x)


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    macd_signal = _ema(macd, signal)
    hist = macd - macd_signal
    return pd.DataFrame({"macd": macd, "macd_signal": macd_signal, "macd_hist": hist})


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return atr.rename("atr")


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    obv = (direction * volume.fillna(0.0)).cumsum()
    return obv.rename("obv")


def calc_bbands(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(period, min_periods=period).mean()
    sd = close.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + std_mult * sd
    lower = mid - std_mult * sd
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower})


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.ewm(alpha=1 / period, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.rename("rsi")


def enrich_indicators(rates: pd.DataFrame) -> pd.DataFrame:
    out = rates.copy()
    macd = calc_macd(out["close"])
    bb = calc_bbands(out["close"])
    out = out.join(macd).join(bb)
    out["atr"] = calc_atr(out)
    out["rsi"] = calc_rsi(out["close"])
    out["obv"] = calc_obv(out["close"], out["tick_volume"])
    out["obv_ma"] = out["obv"].rolling(20, min_periods=20).mean()
    out["ema50"] = _ema(out["close"], 50)
    return out


def mt5_timeframe(name: TimeframeName) -> int:
    m = _require_mt5()
    mapping = {"H4": m.TIMEFRAME_H4, "H1": m.TIMEFRAME_H1, "M15": m.TIMEFRAME_M15}
    return mapping[name]


def connect_mt5() -> None:
    m = _require_mt5()
    if not m.initialize():
        raise RuntimeError(f"MT5 initialize failed: {m.last_error()}")


def shutdown_mt5() -> None:
    if mt5 is None:
        return
    try:
        mt5.shutdown()
    except Exception:
        return


def _resolve_symbol(requested: str) -> str:
    m = _require_mt5()
    if m.symbol_info(requested) is not None:
        return requested
    cands = m.symbols_get(f"*{requested}*")
    if cands:
        return cands[0].name
    raise RuntimeError(f"Symbol not found on broker: {requested}")


def fetch_rates(symbol: str, timeframe: TimeframeName, start: datetime, end: datetime) -> pd.DataFrame:
    m = _require_mt5()
    sym = _resolve_symbol(symbol)
    if not m.symbol_select(sym, True):
        raise RuntimeError(f"symbol_select failed for {sym}: {m.last_error()}")
    rates = m.copy_rates_range(sym, mt5_timeframe(timeframe), start, end)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No rates returned for {sym} {timeframe}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(
        columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "tick_volume": "tick_volume",
            "spread": "spread",
            "real_volume": "real_volume",
        }
    )
    return df.set_index("time").sort_index()


def _calendar_supported() -> bool:
    m = _require_mt5()
    return any(hasattr(m, name) for name in ("calendar_events", "calendar_values", "calendar_event_by_id"))


def fetch_high_impact_events(start: datetime, end: datetime) -> list[dict[str, Any]]:
    m = _require_mt5()
    if not _calendar_supported():
        return []
    events: list[dict[str, Any]] = []
    if hasattr(m, "calendar_values") and hasattr(m, "calendar_events"):
        values = m.calendar_values(start, end)
        if values is None:
            return []
        values_df = pd.DataFrame(list(values))
        if values_df.empty:
            return []
        for _, row in values_df.iterrows():
            importance = row.get("importance")
            if importance is None:
                continue
            if int(importance) < 2:
                continue
            event_id = row.get("event_id")
            ev = None
            if event_id is not None and hasattr(m, "calendar_event_by_id"):
                ev = m.calendar_event_by_id(int(event_id))
            ev_dict: dict[str, Any] = {}
            if ev is not None:
                try:
                    ev_dict = dict(ev._asdict())
                except Exception:
                    ev_dict = {}
            ts_raw = row.get("time")
            ts = None
            try:
                ts = datetime.fromtimestamp(int(ts_raw), tz=UTC)
            except Exception:
                ts = None
            events.append(
                {
                    "time": _ts(ts) if ts else None,
                    "importance": int(importance),
                    "currency": ev_dict.get("currency"),
                    "country": ev_dict.get("country"),
                    "name": ev_dict.get("name"),
                    "actual": row.get("actual"),
                    "forecast": row.get("forecast"),
                    "previous": row.get("previous"),
                }
            )
    return [e for e in events if e.get("time") is not None]


def mark_news_window(index: pd.DatetimeIndex, events: list[dict[str, Any]], window_min: int = 30) -> pd.Series:
    if not events:
        return pd.Series(False, index=index, name="near_high_impact_news")
    event_times = [pd.Timestamp(e["time"]).tz_convert("UTC") for e in events if e.get("time")]
    flags = pd.Series(False, index=index)
    w = pd.Timedelta(minutes=window_min)
    for t in event_times:
        flags |= (index >= (t - w)) & (index <= (t + w))
    return flags.rename("near_high_impact_news")


def compute_confluence(h4: pd.DataFrame, h1: pd.DataFrame, m15: pd.DataFrame) -> pd.Series:
    h4_trend = (h4["close"] > h4["ema50"]) & (h4["macd_hist"] > 0)
    h1_trend = (h1["close"] > h1["ema50"]) & (h1["macd_hist"] > 0)
    h4_bear = (h4["close"] < h4["ema50"]) & (h4["macd_hist"] < 0)
    h1_bear = (h1["close"] < h1["ema50"]) & (h1["macd_hist"] < 0)
    h4_state = pd.Series(np.where(h4_trend, 1, np.where(h4_bear, -1, 0)), index=h4.index)
    h1_state = pd.Series(np.where(h1_trend, 1, np.where(h1_bear, -1, 0)), index=h1.index)
    h4_aligned = h4_state.reindex(m15.index, method="ffill").fillna(0).astype(int)
    h1_aligned = h1_state.reindex(m15.index, method="ffill").fillna(0).astype(int)
    return (h4_aligned + h1_aligned).rename("confluence_score")


def detect_setups(symbol: str, m15: pd.DataFrame) -> pd.DataFrame:
    df = m15.copy()
    prev_close = df["close"].shift(1)
    prev_lower = df["bb_lower"].shift(1)
    prev_upper = df["bb_upper"].shift(1)
    cross_lower = (prev_close >= prev_lower) & (df["close"] < df["bb_lower"])
    cross_upper = (prev_close <= prev_upper) & (df["close"] > df["bb_upper"])
    obv_confirm = (df["obv"] > df["obv"].shift(1)) & (df["obv"] > df["obv_ma"])
    obv_confirm_sell = (df["obv"] < df["obv"].shift(1)) & (df["obv"] < df["obv_ma"])
    buy = cross_lower & (df["rsi"] < 30) & obv_confirm & (df["confluence_score"] >= 1) & (~df["near_high_impact_news"])
    sell = cross_upper & (df["rsi"] > 70) & obv_confirm_sell & (df["confluence_score"] <= -1) & (~df["near_high_impact_news"])
    out = pd.DataFrame(index=df.index)
    out["setup_side"] = np.where(buy, "buy", np.where(sell, "sell", ""))
    out["is_sniper"] = (out["setup_side"] != "").astype(bool)
    return out


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity / peak) - 1.0
    return float(dd.min()) if len(dd) else 0.0


def backtest_sniper(m15: pd.DataFrame, setup: pd.DataFrame, atr_sl_mult: float = 1.5, atr_tp_mult: float = 3.0) -> tuple[BacktestStats, list[SetupEvent]]:
    df = m15.join(setup, how="left")
    df = df.dropna(subset=["atr", "bb_upper", "bb_lower", "rsi", "macd_hist", "obv", "confluence_score", "near_high_impact_news"])
    trades: list[float] = []
    equity = [1.0]
    events: list[SetupEvent] = []
    i = 0
    idx = df.index
    while i < len(df) - 2:
        row = df.iloc[i]
        side = str(row.get("setup_side") or "")
        if side not in ("buy", "sell"):
            i += 1
            continue
        entry_i = i + 1
        entry_row = df.iloc[entry_i]
        entry = float(entry_row["open"])
        atr = float(entry_row["atr"])
        if not (math.isfinite(entry) and math.isfinite(atr) and atr > 0):
            i += 1
            continue
        if side == "buy":
            sl = entry - atr_sl_mult * atr
            tp = entry + atr_tp_mult * atr
        else:
            sl = entry + atr_sl_mult * atr
            tp = entry - atr_tp_mult * atr
        exit_price = None
        exit_i = None
        j = entry_i
        while j < len(df):
            bar = df.iloc[j]
            high = float(bar["high"])
            low = float(bar["low"])
            if side == "buy":
                sl_hit = low <= sl
                tp_hit = high >= tp
                if sl_hit and tp_hit:
                    exit_price = sl
                    exit_i = j
                    break
                if sl_hit:
                    exit_price = sl
                    exit_i = j
                    break
                if tp_hit:
                    exit_price = tp
                    exit_i = j
                    break
            else:
                sl_hit = high >= sl
                tp_hit = low <= tp
                if sl_hit and tp_hit:
                    exit_price = sl
                    exit_i = j
                    break
                if sl_hit:
                    exit_price = sl
                    exit_i = j
                    break
                if tp_hit:
                    exit_price = tp
                    exit_i = j
                    break
            j += 1
        if exit_price is None or exit_i is None:
            break
        ret = (exit_price - entry) / entry if side == "buy" else (entry - exit_price) / entry
        trades.append(float(ret))
        equity.append(equity[-1] * (1.0 + float(ret)))
        events.append(
            SetupEvent(
                symbol="",
                timeframe="M15",
                ts=str(idx[i].to_pydatetime().isoformat()),
                side=cast(Literal["buy", "sell"], side),
                close=_safe_float(row["close"]),
                rsi=_safe_float(row["rsi"]),
                bb_upper=_safe_float(row["bb_upper"]),
                bb_lower=_safe_float(row["bb_lower"]),
                atr=_safe_float(row["atr"]),
                macd_hist=_safe_float(row["macd_hist"]),
                obv=_safe_float(row["obv"]),
                confluence_ok=bool(row["confluence_score"] != 0),
                near_high_impact_news=bool(row["near_high_impact_news"]),
            )
        )
        i = exit_i + 1
    equity_s = pd.Series(equity)
    net_profit = float(equity_s.iloc[-1] - 1.0) if len(equity_s) else 0.0
    if len(trades) >= 2 and float(np.std(trades, ddof=1)) > 0:
        sharpe = float(np.mean(trades) / np.std(trades, ddof=1) * math.sqrt(len(trades)))
    else:
        sharpe = 0.0
    mdd = _max_drawdown(equity_s)
    return BacktestStats(trades=len(trades), net_profit=net_profit, sharpe=sharpe, max_drawdown=mdd), events


def run(symbols: list[str] | None = None, months: int = 6) -> dict[str, Any]:
    connect_mt5()
    try:
        now = datetime.now(tz=UTC)
        start = now - timedelta(days=30 * months)
        cal_events = fetch_high_impact_events(start, now + timedelta(days=1))
        symbols = symbols or ["EURUSD", "XAUUSD", "BTCUSD", "US30"]
        output: dict[str, Any] = {"generated_at": _ts(now), "calendar_high_impact": cal_events, "symbols": {}}
        for sym in symbols:
            h4 = enrich_indicators(fetch_rates(sym, "H4", start, now))
            h1 = enrich_indicators(fetch_rates(sym, "H1", start, now))
            m15_raw = fetch_rates(sym, "M15", start, now)
            m15 = enrich_indicators(m15_raw)
            m15["near_high_impact_news"] = mark_news_window(m15.index, cal_events)
            m15["confluence_score"] = compute_confluence(h4, h1, m15)
            setup = detect_setups(sym, m15)
            stats, events = backtest_sniper(m15, setup)
            events_out = []
            for ev in events[-250:]:
                evd = asdict(ev)
                evd["symbol"] = sym
                events_out.append(evd)
            last = m15.iloc[-1]
            output["symbols"][sym] = {
                "resolved_symbol": _resolve_symbol(sym),
                "timeframes": {
                    "H4": {"last": h4.iloc[-1].dropna().to_dict()},
                    "H1": {"last": h1.iloc[-1].dropna().to_dict()},
                    "M15": {"last": last.dropna().to_dict()},
                },
                "sniper_backtest": asdict(stats),
                "sniper_setups": events_out,
            }
        return output
    finally:
        shutdown_mt5()


def main() -> None:
    out = run()
    path = Path("comprehensive_market_analysis.json")
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
