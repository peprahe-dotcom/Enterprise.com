from __future__ import annotations

import json
import os
import platform
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from godtierbot import __version__
from godtierbot.paths import ensure_dirs, program_data_dir
from godtierbot.redact import redact_text


def _read_tail_bytes(path: Path, max_bytes: int) -> bytes:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read()
    except FileNotFoundError:
        return b""


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def export_support_bundle(app_name: str = "GodTierBot") -> Path:
    base = program_data_dir(app_name)
    dirs = ensure_dirs(base)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_zip = dirs["support_bundles"] / f"{app_name}_Support_{ts}.zip"

    tmp_root = dirs["cache"] / f"support_tmp_{ts}"
    tmp_root.mkdir(parents=True, exist_ok=True)

    docs_src = Path(__file__).resolve().parents[1] / "docs"
    docs_dst = tmp_root / "docs"
    docs_dst.mkdir(parents=True, exist_ok=True)
    for name in ["MASTER_SPEC.md", "PROGRESS.md", "CURRENT_TASK.md", "SECURITY.md"]:
        src = docs_src / name
        if src.exists():
            docs_dst.joinpath(name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    version_payload = {
        "app_version": __version__,
        "schema_version": 1,
    }
    _write_json(tmp_root / "VERSION.json", version_payload)

    env_payload = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "timezone": str(datetime.now().astimezone().tzinfo),
    }
    _write_json(tmp_root / "ENVIRONMENT.json", env_payload)

    config_template = tmp_root / "CONFIG_TEMPLATE.txt"
    settings_path = dirs["config"] / "settings.yaml"
    if settings_path.exists():
        config_template.write_text(redact_text(settings_path.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        config_template.write_text("settings.yaml not found\n", encoding="utf-8")

    logs_dst = tmp_root / "logs"
    logs_dst.mkdir(parents=True, exist_ok=True)
    max_log_bytes = 5 * 1024 * 1024
    for log_name in ["app.log", "updater.log", "bridge.log", "risk.log"]:
        raw = _read_tail_bytes(dirs["logs"] / log_name, max_log_bytes)
        if raw:
            logs_dst.joinpath(log_name).write_text(redact_text(raw.decode("utf-8", errors="replace")), encoding="utf-8")

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in tmp_root.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(tmp_root))

    for p in sorted(tmp_root.rglob("*"), reverse=True):
        if p.is_file():
            p.unlink(missing_ok=True)
        elif p.is_dir():
            p.rmdir()
    tmp_root.rmdir()

    return out_zip

