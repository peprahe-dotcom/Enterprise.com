from __future__ import annotations

import importlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np


try:
    mt5 = importlib.import_module("MetaTrader5")
except Exception:
    mt5 = None


@dataclass(frozen=True)
class TerminalAccount:
    terminal_path: str | None
    login: int
    password_env: str
    server: str


@dataclass(frozen=True)
class SlaveSpec(TerminalAccount):
    name: str
    lot_multiplier: float
    max_positions_total: int


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _require_mt5() -> Any:
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 Python package is not importable. Run this on Windows with MT5 terminal installed."
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


def _load_rules() -> dict[str, Any]:
    raw = _read_json(Path("ai_live_rules.json"))
    return raw if isinstance(raw, dict) else {}


def _global_blocked(rules: dict[str, Any]) -> bool:
    g = rules.get("global") if isinstance(rules.get("global"), dict) else {}
    return bool(g.get("block_all_trading", False))


def _symbol_blocked(rules: dict[str, Any], symbol: str) -> bool:
    s = rules.get("symbols") if isinstance(rules.get("symbols"), dict) else {}
    r = s.get(symbol) if isinstance(s.get(symbol), dict) else {}
    if not bool(r.get("allow_trade", True)):
        return True
    if bool(r.get("low_probability", False)):
        return True
    blocked = r.get("blocked_hours_utc", [])
    if isinstance(blocked, list):
        h = _now().hour
        for x in blocked:
            if isinstance(x, (int, float)) and int(x) == h:
                return True
    return False


def _password_from_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _connect(acct: TerminalAccount) -> None:
    m = _require_mt5()
    init_kwargs: dict[str, Any] = {}
    if acct.terminal_path:
        init_kwargs["path"] = acct.terminal_path
    if not m.initialize(**init_kwargs):
        raise RuntimeError(f"MT5 initialize failed: {m.last_error()}")
    pwd = _password_from_env(acct.password_env)
    if not m.login(int(acct.login), password=pwd, server=str(acct.server)):
        raise RuntimeError(f"MT5 login failed: {m.last_error()}")


def _shutdown() -> None:
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


def _positions_total() -> int:
    m = _require_mt5()
    n = m.positions_total()
    return int(n or 0)


def _order_send_best_effort(request: dict[str, Any]) -> dict[str, Any] | None:
    m = _require_mt5()
    info = m.symbol_info(str(request.get("symbol")))
    fill_modes = []
    fm = int(getattr(info, "filling_mode", 0) or 0) if info is not None else 0
    if fm:
        fill_modes.append(fm)
    for candidate in (getattr(m, "ORDER_FILLING_FOK", 0), getattr(m, "ORDER_FILLING_IOC", 1), getattr(m, "ORDER_FILLING_RETURN", 2)):
        if candidate not in fill_modes:
            fill_modes.append(int(candidate))
    for mode in fill_modes:
        req = dict(request)
        req["type_filling"] = int(mode)
        chk = m.order_check(req)
        if chk is None:
            continue
        retcode = int(getattr(chk, "retcode", -1))
        if retcode not in (0, getattr(m, "TRADE_RETCODE_DONE", 10009), getattr(m, "TRADE_RETCODE_PLACED", 10008)):
            continue
        res = m.order_send(req)
        if res is None:
            continue
        return dict(res._asdict()) if hasattr(res, "_asdict") else {"result": str(res)}
    return None


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
        vol = np.floor(vol / step) * step
    return float(round(float(vol), 8))


def _state_path() -> Path:
    return Path("copier_state.json")


def _load_state() -> dict[str, Any]:
    raw = _read_json(_state_path())
    return raw if isinstance(raw, dict) else {"copied": {}}


def _save_state(state: dict[str, Any]) -> None:
    _atomic_write_json(_state_path(), state)


def _mark_copied(state: dict[str, Any], slave_name: str, master_ticket: int) -> None:
    copied = state.get("copied")
    if not isinstance(copied, dict):
        copied = {}
        state["copied"] = copied
    s = copied.get(slave_name)
    if not isinstance(s, list):
        s = []
        copied[slave_name] = s
    s.append(int(master_ticket))
    s[:] = s[-2000:]


def _already_copied(state: dict[str, Any], slave_name: str, master_ticket: int) -> bool:
    copied = state.get("copied")
    if not isinstance(copied, dict):
        return False
    s = copied.get(slave_name)
    if not isinstance(s, list):
        return False
    return int(master_ticket) in {int(x) for x in s if isinstance(x, (int, float))}


def _copy_position_to_slave(pos: Any, slave: SlaveSpec, magic: int) -> dict[str, Any] | None:
    m = _require_mt5()
    sym = _resolve_symbol(str(pos.symbol))
    if not m.symbol_select(sym, True):
        return None
    volume = float(pos.volume) * float(slave.lot_multiplier)
    volume = _normalize_volume(sym, volume)
    if volume <= 0:
        return None
    tick = m.symbol_info_tick(sym)
    if tick is None:
        return None
    if int(pos.type) == m.POSITION_TYPE_BUY:
        order_type = m.ORDER_TYPE_BUY
        price = float(tick.ask)
    else:
        order_type = m.ORDER_TYPE_SELL
        price = float(tick.bid)
    request = {
        "action": m.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(volume),
        "type": int(order_type),
        "price": float(price),
        "sl": float(pos.sl) if float(pos.sl) > 0 else 0.0,
        "tp": float(pos.tp) if float(pos.tp) > 0 else 0.0,
        "deviation": 30,
        "magic": int(magic),
        "comment": f"copy:{slave.name}:{int(pos.ticket)}",
        "type_time": int(getattr(m, "ORDER_TIME_GTC", 0)),
    }
    return _order_send_best_effort(request)


def _load_config(path: Path) -> tuple[int, TerminalAccount, list[SlaveSpec], int]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise RuntimeError("copier_config.json not found or invalid. Use copier_config.example.json as template.")
    poll_seconds = int(raw.get("poll_seconds", 5) or 5)
    poll_seconds = max(1, min(poll_seconds, 60))
    magic = int(raw.get("magic", 26052402) or 26052402)
    master_raw = raw.get("master") if isinstance(raw.get("master"), dict) else {}
    master = TerminalAccount(
        terminal_path=str(master_raw.get("terminal_path")) if master_raw.get("terminal_path") else None,
        login=int(master_raw.get("login", 0) or 0),
        password_env=str(master_raw.get("password_env", "MT5_MASTER_PASSWORD") or "MT5_MASTER_PASSWORD"),
        server=str(master_raw.get("server", "") or ""),
    )
    slaves_raw = raw.get("slaves") if isinstance(raw.get("slaves"), list) else []
    slaves: list[SlaveSpec] = []
    for s in slaves_raw:
        if not isinstance(s, dict):
            continue
        slaves.append(
            SlaveSpec(
                name=str(s.get("name", "slave") or "slave"),
                terminal_path=str(s.get("terminal_path")) if s.get("terminal_path") else None,
                login=int(s.get("login", 0) or 0),
                password_env=str(s.get("password_env", "") or ""),
                server=str(s.get("server", "") or ""),
                lot_multiplier=float(s.get("lot_multiplier", 1.0) or 1.0),
                max_positions_total=int(s.get("max_positions_total", 1) or 1),
            )
        )
    return poll_seconds, master, slaves, magic


def main() -> None:
    poll_seconds, master, slaves, magic = _load_config(Path("copier_config.json"))
    if not master.server:
        raise RuntimeError("Master server is empty in copier_config.json")
    if not slaves:
        raise RuntimeError("No slaves configured in copier_config.json")
    for s in slaves:
        if not s.password_env or not s.server:
            raise RuntimeError(f"Slave config missing password_env/server: {s.name}")

    while True:
        rules = _load_rules()
        if _global_blocked(rules):
            time.sleep(poll_seconds)
            continue

        state = _load_state()
        try:
            _connect(master)
            m = _require_mt5()
            positions = m.positions_get()
            if positions is None:
                positions = []
            master_positions = list(positions)
        finally:
            _shutdown()

        for pos in master_positions:
            try:
                sym = str(pos.symbol)
                if _symbol_blocked(rules, sym):
                    continue
                master_ticket = int(pos.ticket)
                for slave in slaves:
                    if _already_copied(state, slave.name, master_ticket):
                        continue
                    try:
                        _connect(slave)
                        if slave.max_positions_total > 0 and _positions_total() >= slave.max_positions_total:
                            continue
                        res = _copy_position_to_slave(pos, slave, magic)
                        if res is not None:
                            _mark_copied(state, slave.name, master_ticket)
                            _save_state(state)
                    finally:
                        _shutdown()
            except Exception:
                continue

        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
