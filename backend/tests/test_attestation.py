from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from attestation import verify_chain as vc
from attestation.chain import Attestor
from attestation.keys import AttestationKeyError, load_or_create, public_pem
from attestation.netsnap import default_routes_linux, snapshot
from db.models import AttestationBlock
from tests.conftest import Env
from tests.fakes import CONNECTED_NET, ISOLATED_NET

POLICY = {"mode": "strict", "allow": ["docker0", "br-*"]}


def add(att: Attestor, n: int = 1) -> list[dict[str, Any]]:
    return [
        att.append(
            "alice", f"question {i}", ["a" * 64], f"answer {i}", [{"filename": "x.pdf", "page": 1}], "answered:grounded"
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------- policy


def test_policy_isolated_with_docker_bridge_only() -> None:
    assert vc.evaluate_isolation(ISOLATED_NET, POLICY) == (True, [])


def test_policy_flags_physical_route_and_tunnels() -> None:
    ok, reasons = vc.evaluate_isolation(CONNECTED_NET, POLICY)
    assert not ok
    assert "IPv4 default route present" in reasons
    assert any("physical interface eth0" in r for r in reasons)
    tun = {"interfaces": [{"name": "wg0", "up": True, "kind": "virtual"}], "default_route_v4": False}
    assert not vc.evaluate_isolation(tun, {"mode": "lan", "allow": ["*"]})[0]


def test_lan_mode_allows_listed_physical_without_route() -> None:
    net = {"interfaces": [{"name": "eth1", "up": True, "kind": "physical"}], "default_route_v4": False}
    assert vc.evaluate_isolation(net, {"mode": "lan", "allow": ["eth1"]})[0]
    assert not vc.evaluate_isolation(net, {"mode": "strict", "allow": ["eth1"]})[0]


# ---------------------------------------------------------------- chain


def test_clean_chain_verifies(env: Env) -> None:
    add(env.services.attestor, 5)
    r = env.services.attestor.verify()
    assert (r.valid, r.blocks, r.first_not_isolated, r.exit_code) == (True, 5, None, 0)


def test_tampered_block_detected(env: Env) -> None:
    att = env.services.attestor
    add(att, 4)
    with env.services.db.session() as s:
        row = s.get(AttestationBlock, 2)
        assert row is not None
        body = json.loads(row.body)
        body["answer_hash"] = "f" * 64  # someone rewrites what was answered
        row.body = json.dumps(body)
        s.commit()
    r = att.verify()
    assert not r.valid and r.first_broken == 2 and "block_hash mismatch" in (r.broken_reason or "")


def test_deleted_block_detected(env: Env) -> None:
    att = env.services.attestor
    add(att, 4)
    with env.services.db.session() as s:
        s.delete(s.get(AttestationBlock, 1))
        s.commit()
    r = att.verify()
    assert not r.valid and r.first_broken == 2 and "prev_hash" in (r.broken_reason or "")


def test_resigned_forgery_with_other_key_detected(env: Env) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    att = env.services.attestor
    blocks = [b for b in add(att, 2)]
    forged = dict(blocks[1])
    forged["isolated"] = True
    forged["block_hash"] = vc.compute_block_hash(forged)
    other = Ed25519PrivateKey.generate()
    import base64

    forged["sig"] = base64.b64encode(other.sign(bytes.fromhex(forged["block_hash"]))).decode()
    r = vc.verify_blocks([blocks[0], forged], att.public_key)
    assert not r.valid and r.broken_reason == "invalid signature"


def test_isolation_break_latches_until_acknowledged(env: Env) -> None:
    att, mon, net = env.services.attestor, env.services.monitor, env.net
    add(att, 2)
    net.current = CONNECTED_NET
    b2 = add(att)[0]
    assert b2["isolated"] is False and b2["monitor_state"] == "NOT-ISOLATED"
    net.current = ISOLATED_NET  # cable unplugged again...
    b3 = add(att)[0]
    assert b3["isolated"] is True and b3["monitor_state"] == "NOT-ISOLATED"  # ...but still flagged
    with pytest.raises(RuntimeError):
        net.current = CONNECTED_NET
        mon.acknowledge("admin")  # cannot acknowledge while still connected
    net.current = ISOLATED_NET
    assert mon.acknowledge("admin")["state"] == "ISOLATED"
    b4 = add(att)[0]
    assert b4["monitor_state"] == "ISOLATED"
    r = att.verify()
    assert r.valid and r.first_not_isolated == 2 and r.not_isolated_count == 2 and r.exit_code == 2


def test_status_reports_live_verdict_alongside_latch(env: Env) -> None:
    mon, net = env.services.monitor, env.net
    net.current = CONNECTED_NET
    mon.check_once()
    assert mon.status()["state"] == "NOT-ISOLATED" and mon.status()["isolated_now"] is False
    net.current = ISOLATED_NET  # internet cut: live verdict recovers, latch holds until acknowledged
    mon.check_once()
    s = mon.status()
    assert s["state"] == "NOT-ISOLATED" and s["isolated_now"] is True and s["current_reasons"] == []


def test_monitor_thread_detects_break(env: Env) -> None:
    import time

    mon = env.services.monitor
    mon.start()
    try:
        env.net.current = CONNECTED_NET
        deadline = time.monotonic() + 3
        while mon.state == "ISOLATED" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert mon.state == "NOT-ISOLATED"
        assert mon.status()["break"]["reasons"]
    finally:
        mon.stop()


# ---------------------------------------------------------------- standalone CLI


def test_cli_on_exported_chain(env: Env, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    att = env.services.attestor
    add(att, 3)
    chain = tmp_path / "chain.jsonl"
    pub = tmp_path / "attestation.pub"
    chain.write_text(att.export_jsonl(), encoding="utf-8")
    pub.write_bytes(public_pem(att.public_key))
    assert vc.main([str(chain), "--pubkey", str(pub)]) == 0
    assert "chain integrity: OK" in capsys.readouterr().out

    lines = chain.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"isolated":true', '"isolated":false')
    chain.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert vc.main([str(chain), "--pubkey", str(pub), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["first_broken"] == 1

    assert vc.main([str(tmp_path / "missing.jsonl"), "--pubkey", str(pub)]) == 3


def test_floats_rejected_in_signed_blocks() -> None:
    with pytest.raises(ValueError):
        vc.canonical_json({"score": 0.5})


# ---------------------------------------------------------------- keys + snapshot


def test_key_encrypted_at_rest_and_wrong_passphrase_rejected(tmp_path: Path) -> None:
    key = load_or_create(tmp_path, b"correct horse battery")
    pem = (tmp_path / "attestation.key").read_bytes()
    assert b"ENCRYPTED PRIVATE KEY" in pem
    again = load_or_create(tmp_path, b"correct horse battery")
    assert public_pem(again.public_key()) == public_pem(key.public_key())
    with pytest.raises(AttestationKeyError):
        load_or_create(tmp_path, b"wrong passphrase")


def test_default_route_parsing(tmp_path: Path) -> None:
    (tmp_path / "route").write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
        "eth0\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\n"
    )
    (tmp_path / "ipv6_route").write_text(
        "00000000000000000000000000000000 00 00000000000000000000000000000000 00 "
        "00000000000000000000000000000000 ffffffff 00000001 00000000 00200200 lo\n"
    )
    assert default_routes_linux(tmp_path) == (True, False)
    (tmp_path / "route").write_text("Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n")
    assert default_routes_linux(tmp_path) == (False, False)


def test_real_snapshot_shape() -> None:
    snap = snapshot()
    assert set(snap) == {"platform", "interfaces", "default_route_v4", "default_route_v6"}
    for iface in snap["interfaces"]:
        assert set(iface) == {"name", "up", "admin_up", "oper", "addrs", "kind"}
        assert iface["up"] == (iface["admin_up"] and iface["oper"] not in ("down", "lowerlayerdown", "notpresent"))
        assert iface["name"] != "lo"
    vc.canonical_json(snap)  # must be signable (no floats)


def test_operstate_reading(tmp_path: Path) -> None:
    from attestation.netsnap import operstate

    (tmp_path / "enp0s3").mkdir()
    (tmp_path / "enp0s3" / "operstate").write_text("down\n")
    (tmp_path / "wlan0").mkdir()
    (tmp_path / "wlan0" / "operstate").write_text("up\n")
    assert operstate("enp0s3", tmp_path) == "down"  # cable unplugged: admin-up but cannot carry traffic
    assert operstate("wlan0", tmp_path) == "up"
    assert operstate("missing", tmp_path) == "unknown"
