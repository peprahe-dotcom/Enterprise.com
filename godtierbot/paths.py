from __future__ import annotations

import os
from pathlib import Path


def program_data_dir(app_name: str) -> Path:
    if os.name == "nt":
        root = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(root) / app_name
    return Path.home() / f".{app_name.lower()}"


def ensure_dirs(base: Path) -> dict[str, Path]:
    paths = {
        "base": base,
        "config": base / "config",
        "data": base / "data",
        "models": base / "models",
        "logs": base / "logs",
        "cache": base / "cache",
        "support_bundles": base / "support_bundles",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths
