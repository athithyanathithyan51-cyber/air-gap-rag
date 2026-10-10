from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from api.deps import RateLimiter, Services
from app.config import Settings
from app.main import CheckResult, ReadinessCheck, create_app
from attestation.chain import Attestor
from attestation.monitor import IsolationMonitor
from auth.security import TokenService, hash_password
from db.models import User
from db.session import Database
from rag.vectors import VectorStore
from tests.fakes import DIM, FakeEmbedder, FakeLLM, SwitchableNet

ADMIN_PW = "admin-password-123"
USER_PW = "user-password-123"
POLICY = {"mode": "strict", "allow": ["docker0", "br-*"]}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
        net_guard_enabled=False,
        monitor_enabled=False,
        embed_dim=DIM,
        min_score=0.2,
    )


def static_check(name: str, ok: bool) -> ReadinessCheck:
    async def check() -> CheckResult:
        return CheckResult(name, ok, "stub")

    return check


@dataclass
class Env:
    services: Services
    llm: FakeLLM
    embedder: FakeEmbedder
    net: SwitchableNet


def make_services(tmp_path: Path) -> Env:
    settings = make_settings(tmp_path)
    db = Database(":memory:")
    net = SwitchableNet()
    monitor = IsolationMonitor(db.factory, net, POLICY, 0.05)
    attestor = Attestor(db.factory, Ed25519PrivateKey.generate(), monitor, net)
    llm = FakeLLM()
    embedder = FakeEmbedder()
    svc = Services(
        settings=settings,
        db=db,
        store=VectorStore.in_memory(dim=DIM),
        embedder=embedder,
        llm=llm,
        tokens=TokenService(b"x" * 64, 15, 7),
        monitor=monitor,
        attestor=attestor,
        limiter=RateLimiter(),
    )
    with db.session() as s:
        s.add(User(username="admin", password_hash=hash_password(ADMIN_PW), role="admin"))
        s.add(User(username="alice", password_hash=hash_password(USER_PW), role="user"))
        s.commit()
    return Env(svc, llm, embedder, net)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_services(tmp_path)


@pytest.fixture
def client(tmp_path: Path, env: Env) -> Iterator[TestClient]:
    app = create_app(
        env.services.settings,
        readiness_checks=[static_check("qdrant", True), static_check("ollama", True)],
        frontend_dist=tmp_path / "no-dist",
        services=env.services,
    )
    with TestClient(app) as c:
        yield c


def login(c: TestClient, username: str, password: str) -> dict[str, str]:
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": c.cookies["airgap_csrf"]}
