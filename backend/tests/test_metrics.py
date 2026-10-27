from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.metrics import Registry
from tests.conftest import make_services, make_settings


def _app(tmp_path: Path, enabled: bool) -> FastAPI:
    settings = make_settings(tmp_path).model_copy(update={"metrics_enabled": enabled})
    return create_app(
        settings,
        readiness_checks=[],
        frontend_dist=tmp_path / "no-dist",
        services=make_services(tmp_path).services,
    )


def test_metrics_off_by_default(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, enabled=False)) as c:
        assert c.get("/metrics").status_code == 404


def test_metrics_exposes_request_counts_and_latency(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, enabled=True)) as c:
        c.get("/health")
        c.get("/health")
        c.get("/no-such-page")
        r = c.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert 'airgap_http_requests_total{method="GET",route="/health",status="200"} 2' in body
    assert 'airgap_http_requests_total{method="GET",route="unmatched",status="404"} 1' in body
    assert 'airgap_http_request_duration_seconds_count{method="GET",route="/health",status="200"} 2' in body
    assert 'le="+Inf"' in body


def test_route_template_keeps_ids_out_of_labels(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path, enabled=True)) as c:
        c.get("/api/documents/12345/file")
        c.get("/api/documents/67890/file")
        body = c.get("/metrics").text
    assert 'route="/api/documents/{doc_id}/file"' in body
    assert "12345" not in body
    assert "67890" not in body


def test_histogram_buckets_are_cumulative() -> None:
    reg = Registry()
    reg.observe_request("GET", "/x", 200, 0.03)
    reg.observe_request("GET", "/x", 200, 0.7)
    lines = {ln.split(" ")[0]: ln.split(" ")[1] for ln in reg.render().splitlines() if ln and not ln.startswith("#")}
    key = 'airgap_http_request_duration_seconds_bucket{method="GET",route="/x",status="200"'
    assert lines[key + ',le="0.05"}'] == "1"
    assert lines[key + ',le="1.0"}'] == "2"
    assert lines[key + ',le="+Inf"}'] == "2"
