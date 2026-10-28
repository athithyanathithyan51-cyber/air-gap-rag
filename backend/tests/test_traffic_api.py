from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PW, USER_PW, Env, login
from tests.test_pcap_view import classic_file, tcp_syn_frame

CAPTURE = "20261028T103446Z"


def make_capture(tmp_path: Path, verdict: str = "PASS - zero packets on physical network adapters") -> None:
    folder = tmp_path / "captures" / CAPTURE
    folder.mkdir(parents=True)
    classic_file(folder / "capture.pcapng", [tcp_syn_frame(dport=443), tcp_syn_frame(dport=80), tcp_syn_frame(dport=443)])
    (folder / "verdict.txt").write_text(f"Capture {CAPTURE}\nVERDICT: {verdict}\n", encoding="utf-8")


def test_admin_lists_captures_with_verdict(client: TestClient, env: Env, tmp_path: Path) -> None:
    make_capture(tmp_path)
    h = login(client, "admin", ADMIN_PW)
    rows = client.get("/api/traffic/captures", headers=h).json()
    assert rows == [
        {
            "name": CAPTURE,
            "verdict": "PASS - zero packets on physical network adapters",
            "has_packets": True,
            "size_bytes": (tmp_path / "captures" / CAPTURE / "capture.pcapng").stat().st_size,
        }
    ]


def test_detail_returns_summary_and_pages(client: TestClient, env: Env, tmp_path: Path) -> None:
    make_capture(tmp_path)
    h = login(client, "admin", ADMIN_PW)
    body = client.get(f"/api/traffic/captures/{CAPTURE}?limit=2", headers=h).json()
    assert body["summary"]["packets"] == 3
    assert {p["name"]: p["count"] for p in body["summary"]["protocols"]} == {"HTTPS": 2, "HTTP": 1}
    assert [p["number"] for p in body["packets"]] == [1, 2]
    rest = client.get(f"/api/traffic/captures/{CAPTURE}?offset=2&limit=2", headers=h).json()
    assert [p["number"] for p in rest["packets"]] == [3]


def test_non_admin_is_refused(client: TestClient, env: Env, tmp_path: Path) -> None:
    make_capture(tmp_path)
    h = login(client, "alice", USER_PW)
    assert client.get("/api/traffic/captures", headers=h).status_code == 403
    assert client.get(f"/api/traffic/captures/{CAPTURE}", headers=h).status_code == 403


def test_bad_or_missing_names_are_refused(client: TestClient, env: Env, tmp_path: Path) -> None:
    make_capture(tmp_path)
    h = login(client, "admin", ADMIN_PW)
    assert client.get("/api/traffic/captures/not-a-capture", headers=h).status_code == 400
    assert client.get("/api/traffic/captures/20990101T000000Z", headers=h).status_code == 404
