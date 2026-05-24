from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np

try:
    import ollama
except Exception:
    ollama = None

try:
    import requests
except Exception:
    requests = None


@dataclass(frozen=True)
class SymbolRule:
    allow_trade: bool
    low_probability: bool
    atr_sl_mult: float
    atr_tp_mult: float
    max_spread_points: int
    blocked_hours_utc: list[int]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    return json.loads(raw)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _extract_json_object(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _ollama_generate(model: str, prompt: str) -> str | None:
    if ollama is not None:
        try:
            resp = ollama.generate(model=model, prompt=prompt)
            if isinstance(resp, dict) and "response" in resp:
                return str(resp["response"])
        except Exception:
            return None
    if requests is None:
        return None
    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "response" in data:
            return str(data["response"])
    except Exception:
        return None
    return None


def _default_symbol_rule() -> SymbolRule:
    return SymbolRule(
        allow_trade=True,
        low_probability=False,
        atr_sl_mult=1.5,
        atr_tp_mult=3.0,
        max_spread_points=50,
        blocked_hours_utc=[],
    )


def _validate_symbol_rule(sym: str, raw: dict[str, Any]) -> SymbolRule:
    base = _default_symbol_rule()
    allow_trade = bool(raw.get("allow_trade", base.allow_trade))
    low_probability = bool(raw.get("low_probability", base.low_probability))
    atr_sl_mult = float(raw.get("atr_sl_mult", base.atr_sl_mult))
    atr_tp_mult = float(raw.get("atr_tp_mult", base.atr_tp_mult))
    max_spread_points = int(raw.get("max_spread_points", base.max_spread_points))
    blocked = raw.get("blocked_hours_utc", base.blocked_hours_utc)
    if not isinstance(blocked, list):
        blocked = []
    blocked_hours = sorted({int(x) for x in blocked if isinstance(x, (int, float)) and 0 <= int(x) <= 23})
    atr_sl_mult = float(np.clip(atr_sl_mult, 0.5, 10.0))
    atr_tp_mult = float(np.clip(atr_tp_mult, 0.5, 20.0))
    max_spread_points = int(max(0, min(max_spread_points, 10_000)))
    return SymbolRule(
        allow_trade=allow_trade,
        low_probability=low_probability,
        atr_sl_mult=atr_sl_mult,
        atr_tp_mult=atr_tp_mult,
        max_spread_points=max_spread_points,
        blocked_hours_utc=blocked_hours,
    )


def _safe_rules_from_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "generated_at": _now().isoformat(),
        "global": {"block_all_trading": False, "reason": "", "max_positions_total": 1},
        "risk": {"per_trade_equity_fraction": 0.10},
        "symbols": {},
        "meta": {"last_weekly_review_at": None},
    }
    symbols = analysis.get("symbols") if isinstance(analysis.get("symbols"), dict) else {}
    for sym, payload in symbols.items():
        stats = payload.get("sniper_backtest", {}) if isinstance(payload, dict) else {}
        sharpe = float(stats.get("sharpe", 0.0) or 0.0)
        net_profit = float(stats.get("net_profit", 0.0) or 0.0)
        mdd = float(stats.get("max_drawdown", 0.0) or 0.0)
        low_prob = (sharpe < 0.2) or (net_profit < 0.0) or (mdd < -0.25)
        rule = _default_symbol_rule()
        out["symbols"][sym] = {
            "allow_trade": True,
            "low_probability": bool(low_prob),
            "atr_sl_mult": rule.atr_sl_mult,
            "atr_tp_mult": rule.atr_tp_mult,
            "max_spread_points": rule.max_spread_points,
            "blocked_hours_utc": rule.blocked_hours_utc,
        }
    return out


def _compute_losing_hours_and_symbols(trades: list[dict[str, Any]], min_trades: int = 10) -> tuple[set[str], dict[str, set[int]]]:
    per_symbol: dict[str, list[float]] = {}
    per_sym_hour: dict[tuple[str, int], list[float]] = {}
    for t in trades:
        sym = str(t.get("symbol") or "")
        if not sym:
            continue
        pnl = t.get("pnl")
        if pnl is None:
            continue
        try:
            pnl_f = float(pnl)
        except Exception:
            continue
        ts = t.get("closed_at") or t.get("time") or t.get("opened_at")
        hour = None
        if isinstance(ts, str):
            try:
                hour = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC).hour
            except Exception:
                hour = None
        if hour is None:
            continue
        per_symbol.setdefault(sym, []).append(pnl_f)
        per_sym_hour.setdefault((sym, int(hour)), []).append(pnl_f)
    bad_symbols: set[str] = set()
    bad_hours: dict[str, set[int]] = {}
    for sym, pnls in per_symbol.items():
        if len(pnls) >= min_trades and float(np.mean(pnls)) < 0:
            bad_symbols.add(sym)
    for (sym, hour), pnls in per_sym_hour.items():
        if len(pnls) >= max(5, min_trades // 2) and float(np.mean(pnls)) < 0:
            bad_hours.setdefault(sym, set()).add(hour)
    return bad_symbols, bad_hours


def _apply_blocks_to_rules(rules: dict[str, Any], bad_symbols: set[str], bad_hours: dict[str, set[int]]) -> dict[str, Any]:
    out = dict(rules)
    sym_rules = out.get("symbols")
    if not isinstance(sym_rules, dict):
        out["symbols"] = {}
        sym_rules = out["symbols"]
    for sym in set(sym_rules.keys()) | bad_symbols | set(bad_hours.keys()):
        raw = sym_rules.get(sym, {}) if isinstance(sym_rules.get(sym), dict) else {}
        validated = _validate_symbol_rule(sym, raw)
        if sym in bad_symbols:
            validated = SymbolRule(
                allow_trade=False,
                low_probability=True,
                atr_sl_mult=validated.atr_sl_mult,
                atr_tp_mult=validated.atr_tp_mult,
                max_spread_points=validated.max_spread_points,
                blocked_hours_utc=validated.blocked_hours_utc,
            )
        extra_hours = bad_hours.get(sym, set())
        merged_hours = sorted(set(validated.blocked_hours_utc) | {int(h) for h in extra_hours})
        sym_rules[sym] = {
            "allow_trade": validated.allow_trade,
            "low_probability": validated.low_probability,
            "atr_sl_mult": validated.atr_sl_mult,
            "atr_tp_mult": validated.atr_tp_mult,
            "max_spread_points": validated.max_spread_points,
            "blocked_hours_utc": merged_hours,
        }
    return out


def generate_market_report_and_rules(model: str = "llama3") -> tuple[str, dict[str, Any]]:
    analysis_path = Path("comprehensive_market_analysis.json")
    analysis = _read_json(analysis_path)
    base_rules = _safe_rules_from_analysis(analysis)
    prompt = (
        "You are a senior buy-side risk manager. Read the following JSON market analysis and produce:\n"
        "1) A concise risk report highlighting structural anomalies, regime instability, overfitting risk, and execution risk.\n"
        "2) A SAFE risk payload JSON called ai_live_rules with fields:\n"
        "   global.block_all_trading (bool), global.reason (string), global.max_positions_total (int)\n"
        "   risk.per_trade_equity_fraction (float 0.0-0.10)\n"
        "   symbols.{SYMBOL}.allow_trade (bool), low_probability (bool), atr_sl_mult (0.5-5.0), atr_tp_mult (0.5-10.0), max_spread_points (int), blocked_hours_utc (list of int 0-23)\n"
        "Return the report first, then return ONLY valid JSON on a new line.\n\n"
        f"MARKET_ANALYSIS_JSON:\n{json.dumps(analysis, ensure_ascii=False)}\n\n"
        f"BASE_SAFE_RULES_JSON:\n{json.dumps(base_rules, ensure_ascii=False)}\n"
    )
    resp = _ollama_generate(model, prompt)
    if resp is None:
        report = "Ollama not reachable. Generated deterministic safe rules from backtest statistics.\n"
        return report, base_rules
    parsed = _extract_json_object(resp)
    if not isinstance(parsed, dict):
        report = resp.strip()
        return report, base_rules
    report_part = resp[: resp.find("{")].strip()
    merged = _apply_blocks_to_rules(base_rules, set(), {})
    merged.update({k: v for k, v in parsed.items() if k in ("global", "risk", "symbols", "meta")})
    merged["generated_at"] = _now().isoformat()
    merged["meta"] = merged.get("meta") if isinstance(merged.get("meta"), dict) else {}
    merged["meta"].setdefault("last_weekly_review_at", None)
    return report_part or resp.strip(), merged


def weekly_trade_history_review(rules: dict[str, Any], model: str = "llama3") -> tuple[str, dict[str, Any]]:
    trade_path = Path("live_trade_history.json")
    db = _read_json(trade_path)
    trades = db.get("trades") if isinstance(db.get("trades"), list) else []
    bad_symbols, bad_hours = _compute_losing_hours_and_symbols(trades)
    prompt = (
        "You are a risk controller reviewing a trading journal. Identify underperforming symbols and hours (UTC) and suggest blocks.\n"
        "Return a short text summary, then ONLY valid JSON:\n"
        "{ \"bad_symbols\": [..], \"bad_hours_utc\": {\"SYMBOL\": [hour,..]} }\n\n"
        f"TRADES_JSON:\n{json.dumps(trades, ensure_ascii=False)}\n"
    )
    resp = _ollama_generate(model, prompt)
    if resp is not None:
        parsed = _extract_json_object(resp)
        if isinstance(parsed, dict):
            bs = parsed.get("bad_symbols")
            bh = parsed.get("bad_hours_utc")
            if isinstance(bs, list):
                bad_symbols |= {str(x) for x in bs if isinstance(x, str)}
            if isinstance(bh, dict):
                for k, v in bh.items():
                    if isinstance(k, str) and isinstance(v, list):
                        bad_hours.setdefault(k, set()).update({int(x) for x in v if isinstance(x, (int, float))})
        summary = resp[: resp.find("{")].strip()
    else:
        summary = "Ollama not reachable. Applied deterministic blocks from trade history statistics."
    updated = _apply_blocks_to_rules(rules, bad_symbols, bad_hours)
    updated["meta"] = updated.get("meta") if isinstance(updated.get("meta"), dict) else {}
    updated["meta"]["last_weekly_review_at"] = _now().isoformat()
    updated["generated_at"] = _now().isoformat()
    return summary, updated


def should_run_weekly(rules: dict[str, Any]) -> bool:
    meta = rules.get("meta") if isinstance(rules.get("meta"), dict) else {}
    ts = meta.get("last_weekly_review_at")
    if not isinstance(ts, str) or not ts:
        return True
    try:
        last = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return True
    return _now() - last >= timedelta(days=7)


def main(mode: Literal["market", "weekly"] = "market", model: str = "llama3") -> None:
    insight_path = Path("ai_market_insight.txt")
    rules_path = Path("ai_live_rules.json")
    if mode == "market":
        report, rules = generate_market_report_and_rules(model=model)
        insight_path.write_text(report.strip() + "\n", encoding="utf-8")
        _write_json(rules_path, rules)
        return
    existing = _read_json(rules_path)
    if not isinstance(existing, dict):
        existing = {}
    if not should_run_weekly(existing):
        insight_path.write_text("Weekly review not due.\n", encoding="utf-8")
        return
    summary, updated = weekly_trade_history_review(existing, model=model)
    insight_path.write_text(summary.strip() + "\n", encoding="utf-8")
    _write_json(rules_path, updated)


if __name__ == "__main__":
    main()
