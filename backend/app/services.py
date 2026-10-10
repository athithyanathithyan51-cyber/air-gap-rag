"""Builds the service container from settings."""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from api.deps import RateLimiter, Services
from app.config import Settings
from attestation.chain import Attestor
from attestation.keys import load_or_create, resolve_passphrase
from attestation.monitor import IsolationMonitor
from attestation.netsnap import snapshot
from auth.security import TokenService, hash_password, load_or_create_secret
from db.audit import audit
from db.models import User
from db.session import Database
from rag.ollama import OllamaClient
from rag.vectors import VectorStore

log = logging.getLogger("airgap.app")


def build_services(settings: Settings) -> Services:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    ollama = OllamaClient(
        settings.ollama_url,
        settings.chat_model,
        settings.embed_model,
        settings.llm_timeout_s,
        settings.llm_temperature,
        settings.llm_num_ctx,
    )
    store = VectorStore.connect(settings.qdrant_url, settings.qdrant_collection, settings.embed_dim)
    secret = load_or_create_secret(settings.jwt_secret_file or settings.keys_dir / "jwt.secret")
    tokens = TokenService(secret, settings.access_token_minutes, settings.refresh_token_days)
    policy = {"mode": settings.isolation_mode, "allow": list(settings.isolation_allow)}
    monitor = IsolationMonitor(db.factory, snapshot, policy, settings.monitor_interval_s)
    passphrase = resolve_passphrase(
        settings.attestation_passphrase, settings.attestation_passphrase_file, settings.keys_dir, settings.environment
    )
    attestor = Attestor(db.factory, load_or_create(settings.keys_dir, passphrase), monitor, snapshot)
    bootstrap_admin(db, settings)
    return Services(settings, db, store, ollama, ollama, tokens, monitor, attestor, RateLimiter())


def bootstrap_admin(db: Database, settings: Settings) -> None:
    """Create the first admin from AIRGAP_BOOTSTRAP_ADMIN_PASSWORD if no user exists yet."""
    with db.session() as s:
        if (s.scalar(select(func.count()).select_from(User)) or 0) > 0:
            return
        if not settings.bootstrap_admin_password:
            log.warning("no_users", extra={"hint": "run: python -m app.cli create-user <name> --role admin"})
            return
        name = settings.bootstrap_admin_user.lower()
        s.add(User(username=name, password_hash=hash_password(settings.bootstrap_admin_password), role="admin"))
        s.commit()
        audit(s, "system", "user.bootstrap_admin", username=name)
