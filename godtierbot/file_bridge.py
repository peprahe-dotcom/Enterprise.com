from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godtierbot.paths import ensure_dirs, program_data_dir


@dataclass(frozen=True)
class BridgePaths:
    base: Path
    signals: Path
    confirms: Path


def _default_mt5_common_files_dir() -> Path:
    if os.name != "nt":
        return program_data_dir("GodTierBot") / "mt5_common_files_placeholder"
    appdata = Path(os.environ.get("APPDATA", r"C:\Users\%USERNAME%\AppData\Roaming"))
    return appdata / "MetaQuotes" / "Terminal" / "Common" / "Files"


def bridge_paths(root: Path | None = None) -> BridgePaths:
    root = root or _default_mt5_common_files_dir()
    base = root / "GodTierBot"
    signals = base / "signals"
    confirms = base / "confirms"
    signals.mkdir(parents=True, exist_ok=True)
    confirms.mkdir(parents=True, exist_ok=True)
    return BridgePaths(base=base, signals=signals, confirms=confirms)


def write_signal(account_id: str, payload: dict[str, Any], root: Path | None = None) -> Path:
    paths = bridge_paths(root)
    out = paths.signals / f"{account_id}.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return out


def read_confirm(signal_id: str, timeout_s: float = 10.0, root: Path | None = None) -> dict[str, Any] | None:
    paths = bridge_paths(root)
    p = paths.confirms / f"{signal_id}.json"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            finally:
                try:
                    p.unlink()
                except OSError:
                    pass
        time.sleep(0.1)
    return None


def ensure_programdata_defaults(app_name: str = "GodTierBot") -> None:
    base = program_data_dir(app_name)
    ensure_dirs(base)
