from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from .secrets import SecretsStore, load_or_create_machine_key
from .settings import RuntimeSettings


@dataclass(frozen=True)
class BootstrapResult:
    settings: RuntimeSettings
    first_run: bool


def _random_password() -> str:
    return secrets.token_urlsafe(18)


def _random_token() -> str:
    return secrets.token_urlsafe(32)


def load_settings() -> BootstrapResult:
    s = RuntimeSettings()
    paths = s.paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    key_path = paths.data_dir / "machine.key"
    key = load_or_create_machine_key(key_path)
    store = SecretsStore(paths.secrets_path)

    first_run = not paths.config_path.exists() or not store.exists()

    if not first_run:
        cfg = json.loads(paths.config_path.read_text(encoding="utf-8"))
        sec = store.load_encrypted_json(key)
        return BootstrapResult(
            settings=RuntimeSettings(
                host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 8080)),
                paper_mode=bool(cfg.get("paper_mode", True)),
                admin_password=sec.get("admin_password"),
                mt5_shared_token=sec.get("mt5_shared_token"),
            ),
            first_run=False,
        )

    cfg = {
        "host": s.host,
        "port": s.port,
        "paper_mode": True,
    }
    paths.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    store.save_encrypted_json(
        {
            "admin_password": _random_password(),
            "mt5_shared_token": _random_token(),
        },
        key=key,
    )

    sec = store.load_encrypted_json(key)
    return BootstrapResult(
        settings=RuntimeSettings(
            host=cfg["host"],
            port=cfg["port"],
            paper_mode=True,
            admin_password=sec["admin_password"],
            mt5_shared_token=sec["mt5_shared_token"],
        ),
        first_run=True,
    )

