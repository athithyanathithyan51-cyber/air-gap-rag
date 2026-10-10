"""Runtime settings, read from environment variables prefixed with AIRGAP_."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIRGAP_", env_file=None, extra="ignore")

    app_name: str = "Offline LLM-Based Intelligent Conversational Assistant"
    environment: str = Field(default="production", pattern="^(production|development|test)$")

    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    data_dir: Path = Path("data")
    log_dir: Path = Path("data/logs")
    log_level: str = "INFO"
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    qdrant_url: str = "http://127.0.0.1:6333"
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen2.5:7b-instruct-q4_K_M"
    embed_model: str = "nomic-embed-text"

    # Hosts the process may connect to besides loopback. Empty means loopback only.
    net_allowed_hosts: list[str] = Field(default_factory=list)
    net_guard_enabled: bool = True

    ready_timeout_s: float = 2.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
