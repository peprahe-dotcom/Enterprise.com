from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class SecretsStore:
    secrets_path: Path

    def exists(self) -> bool:
        return self.secrets_path.exists()

    def save_encrypted_json(self, data: dict, key: bytes) -> None:
        self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        f = Fernet(key)
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        token = f.encrypt(payload)
        self.secrets_path.write_bytes(token)

    def load_encrypted_json(self, key: bytes) -> dict:
        token = self.secrets_path.read_bytes()
        f = Fernet(key)
        payload = f.decrypt(token)
        return json.loads(payload.decode("utf-8"))


def generate_key() -> bytes:
    return Fernet.generate_key()


def load_or_create_machine_key(key_path: Path) -> bytes:
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes()
    k = generate_key()
    key_path.write_bytes(k)
    try:
        os.chmod(key_path, 0o600)
    except Exception:
        pass
    return k

