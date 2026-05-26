from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godtierbot.paths import ensure_dirs, program_data_dir


@dataclass(frozen=True)
class StorePaths:
    base: Path
    db_path: Path


def store_paths(app_name: str = "GodTierBot") -> StorePaths:
    base = program_data_dir(app_name)
    dirs = ensure_dirs(base)
    return StorePaths(base=base, db_path=dirs["data"] / "godtierbot.sqlite")


def init_db(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "ts TEXT NOT NULL,"
            "type TEXT NOT NULL,"
            "payload_json TEXT NOT NULL"
            ")"
        )
        con.commit()
    finally:
        con.close()


def log_event(db_path: Path, ts: str, typ: str, payload: dict[str, Any]) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "INSERT INTO events (ts, type, payload_json) VALUES (?, ?, ?)",
            (ts, typ, json.dumps(payload, ensure_ascii=False)),
        )
        con.commit()
    finally:
        con.close()

