#!/usr/bin/env python3
"""Standalone offline verifier for the isolation-attestation chain.

Dependencies: Python 3.10+ standard library and `cryptography`. This file is
self-contained on purpose: an auditor can copy it alone, with the exported
chain (JSONL) and the public key, to any machine and run it without network.

What a valid chain means: a tamper-evident record of network-interface state
at the moment of each answer. It does NOT prove that no packet was ever sent.
Anyone with host access and the signing key can forge a whole new chain.

Usage:
    python verify_chain.py chain.jsonl --pubkey attestation.pub [--json]

Exit codes: 0 valid and every block isolated, 1 chain broken/invalid,
            2 chain valid but contains NOT-ISOLATED blocks, 3 usage/input error.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
GENESIS_PREV = "0" * 64
SIGNED_EXCLUDE = ("block_hash", "sig")
# Interfaces that can carry traffic off the machine; never allowed by any policy.
NEVER_ALLOWED = ("tun*", "tap*", "wg*", "ppp*", "wwan*", "ipsec*", "utun*")


# ---------------------------------------------------------------- canonical form


def canonical_json(obj: Any) -> bytes:
    """Sorted keys, no whitespace, UTF-8. Floats are rejected to keep encoding unambiguous."""

    def check(o: Any) -> None:
        if isinstance(o, float):
            raise ValueError("floats are not allowed in signed blocks")
        if isinstance(o, dict):
            for v in o.values():
                check(v)
        elif isinstance(o, list):
            for v in o:
                check(v)

    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_block_hash(block: dict[str, Any]) -> str:
    body = {k: v for k, v in block.items() if k not in SIGNED_EXCLUDE}
    return hashlib.sha256(canonical_json(body)).hexdigest()


# ---------------------------------------------------------------- isolation policy


def _matches(name: str, patterns: list[str] | tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def evaluate_isolation(net: dict[str, Any], policy: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (isolated, reasons). Pure function shared by the app and this verifier.

    strict: no default route; no physical interface up; every other up interface
            matches policy.allow.
    lan:    no default route; every up interface (physical included) matches policy.allow.
    Tunnel-type interfaces are never allowed.
    """
    reasons: list[str] = []
    mode = policy.get("mode", "strict")
    allow = list(policy.get("allow", []))
    if net.get("default_route_v4"):
        reasons.append("IPv4 default route present")
    if net.get("default_route_v6"):
        reasons.append("IPv6 default route present")
    for iface in net.get("interfaces", []):
        if not iface.get("up"):
            continue
        name = str(iface.get("name", ""))
        kind = iface.get("kind", "physical")
        if _matches(name, NEVER_ALLOWED):
            reasons.append(f"tunnel interface {name} is up")
        elif kind == "physical" and mode == "strict":
            reasons.append(f"physical interface {name} is up")
        elif not _matches(name, allow):
            reasons.append(f"interface {name} ({kind}) is up and not allowlisted")
    return (not reasons, reasons)


# ---------------------------------------------------------------- signatures


def load_public_key(text: str) -> Any:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    text = text.strip()
    if text.startswith("-----BEGIN"):
        key = serialization.load_pem_public_key(text.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("public key is not Ed25519")
        return key
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(text))


def key_id(public_key: Any) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def verify_signature(public_key: Any, block: dict[str, Any]) -> bool:
    from cryptography.exceptions import InvalidSignature

    try:
        public_key.verify(base64.b64decode(block["sig"]), bytes.fromhex(block["block_hash"]))
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
    return True


# ---------------------------------------------------------------- chain verification


@dataclass
class Report:
    blocks: int = 0
    valid: bool = True
    first_broken: int | None = None
    broken_reason: str | None = None
    first_not_isolated: int | None = None
    not_isolated_count: int = 0
    not_isolated_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if not self.valid:
            return 1
        return 2 if self.not_isolated_count else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "blocks": self.blocks,
            "valid": self.valid,
            "first_broken": self.first_broken,
            "broken_reason": self.broken_reason,
            "first_not_isolated": self.first_not_isolated,
            "not_isolated_count": self.not_isolated_count,
            "not_isolated_reasons": self.not_isolated_reasons,
            "warnings": self.warnings,
            "exit_code": self.exit_code,
        }


def check_block(block: dict[str, Any], prev: dict[str, Any] | None, public_key: Any) -> str | None:
    """Return None if the block is internally valid and links to prev, else a reason."""
    required = (
        "v",
        "index",
        "counter",
        "ts_utc",
        "net",
        "policy",
        "isolated",
        "monitor_state",
        "prev_hash",
        "key_id",
        "block_hash",
        "sig",
    )
    missing = [k for k in required if k not in block]
    if missing:
        return f"missing fields: {', '.join(missing)}"
    if block["v"] != SCHEMA_VERSION:
        return f"unsupported schema version {block['v']}"
    if compute_block_hash(block) != block["block_hash"]:
        return "block_hash mismatch (content was modified)"
    if block["key_id"] != key_id(public_key):
        return "signed with a different key"
    if not verify_signature(public_key, block):
        return "invalid signature"
    if prev is None:
        if block["index"] != 0 or block["prev_hash"] != GENESIS_PREV:
            return "first block is not a genesis block"
    else:
        if block["prev_hash"] != prev["block_hash"]:
            return "prev_hash does not match previous block (block removed, inserted or reordered)"
        if block["index"] != prev["index"] + 1:
            return f"index jumps from {prev['index']} to {block['index']}"
        if block["counter"] != prev["counter"] + 1:
            return f"monotonic counter jumps from {prev['counter']} to {block['counter']}"
    isolated, _ = evaluate_isolation(block["net"], block["policy"])
    if isolated != block["isolated"]:
        return "stored isolation verdict does not match its own network snapshot"
    return None


def verify_blocks(blocks: list[dict[str, Any]], public_key: Any) -> Report:
    report = Report(blocks=len(blocks))
    prev: dict[str, Any] | None = None
    for block in blocks:
        reason = check_block(block, prev, public_key)
        if reason is not None:
            report.valid = False
            report.first_broken = int(block.get("index", -1)) if isinstance(block.get("index"), int) else -1
            report.broken_reason = reason
            return report
        if prev is not None and block["ts_utc"] < prev["ts_utc"]:
            report.warnings.append(f"block {block['index']}: timestamp earlier than previous block (clock changed?)")
        if not block["isolated"] or block["monitor_state"] != "ISOLATED":
            report.not_isolated_count += 1
            if report.first_not_isolated is None:
                report.first_not_isolated = block["index"]
                _, reasons = evaluate_isolation(block["net"], block["policy"])
                if block["monitor_state"] != "ISOLATED":
                    reasons.append("isolation monitor recorded an unacknowledged break before this answer")
                report.not_isolated_reasons = reasons
        prev = block
    return report


def read_jsonl(path: str) -> list[dict[str, Any]]:
    blocks = []
    with open(path, encoding="utf-8") as fh:  # noqa: PTH123 - keep stdlib-only and simple
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                blocks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {n}: not valid JSON ({exc.msg})") from exc
    return blocks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify an isolation-attestation chain offline.")
    ap.add_argument("chain", help="exported chain, one JSON block per line")
    ap.add_argument("--pubkey", required=True, help="attestation public key (PEM or base64 raw)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    try:
        with open(args.pubkey, encoding="utf-8") as fh:  # noqa: PTH123
            public_key = load_public_key(fh.read())
        blocks = read_jsonl(args.chain)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    report = verify_blocks(blocks, public_key)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return report.exit_code
    print(f"blocks checked: {report.blocks}")
    if not report.valid:
        print(f"CHAIN BROKEN at block {report.first_broken}: {report.broken_reason}")
    else:
        print("chain integrity: OK (hashes, signatures, links, counters)")
    if report.first_not_isolated is not None:
        print(f"NOT-ISOLATED: {report.not_isolated_count} block(s); first at block {report.first_not_isolated}")
        for r in report.not_isolated_reasons:
            print(f"  - {r}")
    elif report.valid:
        print("isolation: every block recorded ISOLATED")
    for w in report.warnings:
        print(f"warning: {w}")
    print("note: this is a tamper-evident record of interface state at each answer, not proof that no packet was sent.")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
