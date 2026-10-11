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

    # --- model services (loopback only) ---
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "chunks"
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen2.5:7b-instruct-q4_K_M"
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    llm_timeout_s: float = 300.0
    llm_temperature: float = 0.1
    llm_num_ctx: int = 8192

    # --- retrieval / answering ---
    chunk_tokens: int = 800
    chunk_overlap_tokens: int = 100
    top_k: int = 5
    # Cosine similarity below which we refuse without calling the LLM.
    # Default is a starting point; tuned on the gold set (eval/), value recorded in eval/results.
    min_score: float = 0.55
    max_context_chars: int = 16000
    # Below min_score, answer from the model's own knowledge (labelled "general", no citations)
    # instead of refusing. False restores strict documents-only mode.
    general_chat: bool = True

    # --- uploads ---
    max_upload_mb: int = 50
    max_pdf_pages: int = 2000

    # --- auth ---
    jwt_secret_file: Path | None = None
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False  # True once served over local TLS (v1.0.0)
    login_rate_limit: str = "10/minute"
    chat_rate_limit: str = "30/minute"
    bootstrap_admin_user: str = "admin"
    bootstrap_admin_password: str | None = None

    # --- attestation ---
    attestation_passphrase: str | None = None
    attestation_passphrase_file: Path | None = None
    monitor_enabled: bool = True
    monitor_interval_s: float = 1.0
    isolation_allow: list[str] = Field(default_factory=lambda: ["docker0", "br-*"])
    isolation_mode: str = Field(default="strict", pattern="^(strict|lan)$")

    # Hosts the process may connect to besides loopback. Empty means loopback only.
    net_allowed_hosts: list[str] = Field(default_factory=list)
    net_guard_enabled: bool = True

    ready_timeout_s: float = 2.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "airgap.db"

    @property
    def docs_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
