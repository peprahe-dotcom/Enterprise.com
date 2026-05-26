from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from godtierbot import __version__
from godtierbot.paths import ensure_dirs, program_data_dir


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    notes: str
    app_zip_url: str
    app_zip_sha256: str


def _parse_version(v: str) -> tuple[int, int, int]:
    v = v.strip().lstrip("v")
    parts = v.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return major, minor, patch


def is_newer(a: str, b: str) -> bool:
    return _parse_version(a) > _parse_version(b)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json_from_url(url: str, timeout_s: int = 10) -> dict[str, Any]:
    r = requests.get(url, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _load_json_from_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(url_or_path: str) -> dict[str, Any]:
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        return _load_json_from_url(url_or_path)
    return _load_json_from_file(Path(url_or_path))


def get_update_info(manifest: dict[str, Any], current_version: str = __version__) -> UpdateInfo | None:
    latest = str(manifest.get("latest", {}).get("version", "")).strip()
    if not latest:
        return None
    if not is_newer(latest, current_version):
        return None

    notes = str(manifest.get("latest", {}).get("notes", "")).strip()
    assets = manifest.get("latest", {}).get("assets", {})
    app_zip = assets.get("app_update_zip", {})
    app_zip_url = str(app_zip.get("url", "")).strip()
    app_zip_sha256 = str(app_zip.get("sha256", "")).strip()
    if not app_zip_url or not app_zip_sha256:
        return None

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest,
        notes=notes,
        app_zip_url=app_zip_url,
        app_zip_sha256=app_zip_sha256,
    )


def _download(url: str, dest: Path, timeout_s: int = 30) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout_s) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)


def _windows_start_detached(cmd: list[str]) -> None:
    subprocess.Popen(
        cmd,
        close_fds=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,  # type: ignore[attr-defined]
        cwd=str(Path(cmd[0]).parent) if cmd else None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def _write_apply_script(script_path: Path, staging_dir: Path, target_dir: Path, exe_name: str) -> None:
    target_dir_str = str(target_dir)
    staging_dir_str = str(staging_dir)
    exe_path_str = str(target_dir / exe_name)
    script = f"""@echo off
setlocal enabledelayedexpansion

REM Wait a moment for the main process to exit
ping 127.0.0.1 -n 3 >nul

REM Copy staged files over the install dir
robocopy "{staging_dir_str}" "{target_dir_str}" /E /R:3 /W:1 >nul

REM Start the updated app
start "" "{exe_path_str}" version
"""
    script_path.write_text(script, encoding="utf-8")


def apply_update_from_manifest(
    manifest_url_or_path: str,
    app_name: str = "GodTierBot",
    assume_yes: bool = False,
) -> str:
    manifest = load_manifest(manifest_url_or_path)
    info = get_update_info(manifest)
    if not info:
        return "No update available"

    if not assume_yes:
        sys.stdout.write(f"Update available: {info.current_version} -> {info.latest_version}\n")
        if info.notes:
            sys.stdout.write(f"{info.notes}\n")
        sys.stdout.write("Apply update now? [y/N] ")
        sys.stdout.flush()
        ans = sys.stdin.readline().strip().lower()
        if ans not in {"y", "yes"}:
            return "Update cancelled"

    base = program_data_dir(app_name)
    dirs = ensure_dirs(base)

    zip_path = dirs["cache"] / f"{app_name}_app_{info.latest_version}.zip"
    _download(info.app_zip_url, zip_path)

    actual = _sha256(zip_path)
    if actual.lower() != info.app_zip_sha256.lower():
        return "Update failed: SHA256 mismatch"

    exe_path = Path(sys.executable)
    target_dir = exe_path.parent
    exe_name = exe_path.name

    staging_dir = Path(tempfile.mkdtemp(prefix=f"{app_name}_stage_"))
    try:
        _extract_zip(zip_path, staging_dir)

        apply_cmd = dirs["cache"] / f"apply_update_{int(time.time())}.cmd"
        _write_apply_script(apply_cmd, staging_dir, target_dir, exe_name)

        if os.name == "nt":
            _windows_start_detached(["cmd.exe", "/c", str(apply_cmd)])
        else:
            return "Update staged, but apply is only supported on Windows"
    finally:
        pass

    raise SystemExit(0)

