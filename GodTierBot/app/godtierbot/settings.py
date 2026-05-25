from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppPaths(BaseModel):
    data_dir: Path
    config_path: Path
    secrets_path: Path
    db_path: Path
    logs_dir: Path


def default_data_dir() -> Path:
    base = Path.home() / "AppData" / "Local" / "GodTierBot"
    return base


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GODTIERBOT_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8080
    paper_mode: bool = True

    admin_password: str | None = None
    mt5_shared_token: str | None = None

    def paths(self) -> AppPaths:
        data_dir = default_data_dir()
        return AppPaths(
            data_dir=data_dir,
            config_path=data_dir / "config.json",
            secrets_path=data_dir / "secrets.bin",
            db_path=data_dir / "godtier.db",
            logs_dir=data_dir / "logs",
        )


class UiState(BaseModel):
    trading_paused: bool = False
    last_heartbeat_ms: int | None = None
    mt5_connected: bool = False
    mt5_last_account: str | None = None


class Mt5PollRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    token: str | None = None
    terminal: str | None = None
    timestamp_ms: int


class Command(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


class Mt5PollResponse(BaseModel):
    ok: bool
    commands: list[Command] = Field(default_factory=list)
    message: str | None = None
