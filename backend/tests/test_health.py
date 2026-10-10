from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import APP_VERSION, SECURITY_HEADERS, create_app
from tests.conftest import make_services, make_settings, static_check


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": APP_VERSION}
    assert r.headers["cache-control"] == "no-store"


def test_security_headers_present(client: TestClient) -> None:
    r = client.get("/health")
    for key, value in SECURITY_HEADERS.items():
        assert r.headers[key] == value
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_ready_all_ok(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert set(r.json()["checks"]) == {"qdrant", "ollama"}


def test_ready_reports_failure(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path),
        readiness_checks=[static_check("qdrant", True), static_check("ollama", False)],
        frontend_dist=tmp_path / "no-dist",
        services=make_services(tmp_path).services,
    )
    with TestClient(app) as c:
        r = c.get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["ollama"]["ok"] is False


def test_cdn_backed_docs_are_disabled(client: TestClient) -> None:
    # Swagger UI and ReDoc pull JavaScript from public CDNs; they must not exist.
    for path in ("/docs", "/redoc", "/api/openapi.json", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_frontend_served_when_built(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    app = create_app(
        make_settings(tmp_path), readiness_checks=[], frontend_dist=dist, services=make_services(tmp_path).services
    )
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "<title>t</title>" in r.text
    assert r.headers["x-frame-options"] == "DENY"
