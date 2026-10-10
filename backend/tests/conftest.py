from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import CheckResult, ReadinessCheck, create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(environment="test", data_dir=tmp_path, log_dir=tmp_path / "logs", net_guard_enabled=False)


def static_check(name: str, ok: bool) -> ReadinessCheck:
    async def check() -> CheckResult:
        return CheckResult(name, ok, "stub")

    return check


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        make_settings(tmp_path),
        readiness_checks=[static_check("qdrant", True), static_check("ollama", True)],
        frontend_dist=tmp_path / "no-dist",
    )
    with TestClient(app) as c:
        yield c
