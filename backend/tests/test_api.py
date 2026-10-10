from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PW, USER_PW, Env, login
from tests.fakes import CONNECTED_NET

POLICY_MD = b"""# Attendance
Students must maintain a minimum attendance of 75 percent in every course to be eligible for the semester examination.
"""


def sse_events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def upload(c: TestClient, h: dict[str, str], name: str = "policy.md", data: bytes = POLICY_MD) -> Any:
    return c.post("/api/documents", files={"file": (name, data, "application/octet-stream")}, headers=h)


# ---------------------------------------------------------------- auth


def test_login_sets_httponly_cookies_and_me(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    cookies = r.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("airgap_access="))
    refresh = next(c for c in cookies if c.startswith("airgap_refresh="))
    csrf = next(c for c in cookies if c.startswith("airgap_csrf="))
    assert "HttpOnly" in access and "SameSite=strict" in access
    assert "HttpOnly" in refresh and "Path=/api/auth" in refresh
    assert "HttpOnly" not in csrf
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_bad_password_and_unauthenticated(client: TestClient) -> None:
    assert client.post("/api/auth/login", json={"username": "admin", "password": "nope-nope-nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope-nope"}).status_code == 401
    assert client.get("/api/documents").status_code == 401


def test_login_rate_limited(client: TestClient) -> None:
    codes = [client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and 429 in codes[10:]


def test_csrf_required_for_state_changes(client: TestClient) -> None:
    login(client, "admin", ADMIN_PW)
    assert upload(client, {}).status_code == 403
    assert upload(client, {"X-CSRF-Token": "wrong"}).status_code == 403


def test_refresh_rotation_and_reuse_detection(client: TestClient) -> None:
    login(client, "alice", USER_PW)
    old = client.cookies["airgap_refresh"]
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    new = client.cookies["airgap_refresh"]
    assert new != old
    client.cookies.set("airgap_refresh", old, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401  # reuse of rotated token
    client.cookies.set("airgap_refresh", new, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401  # whole family revoked


def test_user_role_cannot_upload_or_admin(client: TestClient) -> None:
    h = login(client, "alice", USER_PW)
    assert upload(client, h).status_code == 403
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/audit").status_code == 403


def test_admin_creates_and_disables_user(client: TestClient) -> None:
    h = login(client, "admin", ADMIN_PW)
    r = client.post(
        "/api/admin/users", json={"username": "bob", "password": "bob-password-1", "role": "user"}, headers=h
    )
    assert r.status_code == 201
    assert (
        client.post("/api/admin/users", json={"username": "bob", "password": "bob-password-1"}, headers=h).status_code
        == 409
    )
    uid = r.json()["id"]
    assert client.patch(f"/api/admin/users/{uid}", json={"active": False}, headers=h).json()["active"] is False
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": "bob", "password": "bob-password-1"}).status_code == 401


# ---------------------------------------------------------------- documents + chat + attestation


def test_end_to_end_answer_with_citation_and_verification(client: TestClient, env: Env) -> None:
    h = login(client, "admin", ADMIN_PW)
    r = upload(client, h)
    assert r.status_code == 201 and r.json()["outcome"] == "ingested"
    assert upload(client, h, "evil.pdf", b"MZ\x00\x01binary").status_code == 415

    client.cookies.clear()
    h = login(client, "alice", USER_PW)
    env.llm.reply = "Students must maintain a minimum attendance of 75 percent in every course [S1]."
    r = client.post("/api/chat", json={"question": "What minimum attendance must students maintain?"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r.text)
    final = events[-1]
    assert final["type"] == "final" and final["status"] == "answered"
    assert final["citations"][0]["filename"] == "policy.md"
    assert final["attestation"]["isolated"] is True
    idx = final["attestation"]["index"]

    chunk = client.get(f"/api/documents/chunks/{final['citations'][0]['chunk_id']}").json()
    assert "75 percent" in chunk["text"]

    v = client.get(f"/api/attestation/blocks/{idx}").json()
    assert v["chain_valid_up_to_block"] is True and v["isolated"] is True
    assert v["block"]["citations"][0]["filename"] == "policy.md"
    assert any("not proof" in lim for lim in v["limits"])


def test_refusal_is_attested_and_break_flagged(client: TestClient, env: Env) -> None:
    h = login(client, "alice", USER_PW)
    env.net.current = CONNECTED_NET
    r = client.post("/api/chat", json={"question": "Who won the 1998 world cup?"}, headers=h)
    final = sse_events(r.text)[-1]
    assert final["status"] == "refused" and final["answer"].startswith("I don't know")
    assert final["attestation"]["isolated"] is False
    assert final["attestation"]["monitor_state"] == "NOT-ISOLATED"
    assert client.get("/api/attestation/status").json()["state"] == "NOT-ISOLATED"


def test_users_cannot_verify_others_blocks(client: TestClient, env: Env) -> None:
    h = login(client, "admin", ADMIN_PW)
    final = sse_events(client.post("/api/chat", json={"question": "anything?"}, headers=h).text)[-1]
    client.cookies.clear()
    login(client, "alice", USER_PW)
    assert client.get(f"/api/attestation/blocks/{final['attestation']['index']}").status_code == 403


def test_llm_down_reports_error(client: TestClient, env: Env) -> None:
    from rag.ollama import LLMUnavailableError

    class Down:
        async def stream_chat(self, messages: list[dict[str, str]]) -> Any:
            raise LLMUnavailableError("connection refused")
            yield ""  # pragma: no cover

    h = login(client, "admin", ADMIN_PW)
    upload(client, h)
    env.services.llm = Down()
    events = sse_events(
        client.post("/api/chat", json={"question": "What minimum attendance is required?"}, headers=h).text
    )
    assert events[-1]["type"] == "error" and "unavailable" in events[-1]["message"]


def test_admin_export_and_audit(client: TestClient) -> None:
    h = login(client, "admin", ADMIN_PW)
    client.post("/api/chat", json={"question": "anything?"}, headers=h)
    export = client.get("/api/attestation/export")
    assert export.status_code == 200 and len(export.text.strip().splitlines()) == 1
    assert "BEGIN PUBLIC KEY" in client.get("/api/attestation/pubkey").text
    actions = [e["action"] for e in client.get("/api/admin/audit").json()]
    assert "chat.answer" in actions and "auth.login" in actions
