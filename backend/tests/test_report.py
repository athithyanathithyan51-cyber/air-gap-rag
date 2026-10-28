from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attestation.report import REPORT_TYPE, build_report
from attestation.verify_chain import canonical_json


def block(index: int, isolated: bool, filename: str) -> dict[str, Any]:
    return {
        "index": index,
        "ts_utc": "2026-10-29T10:00:00.000Z",
        "block_hash": f"{index:064x}",
        "query_hash": "a" * 64,
        "answer_hash": "b" * 64,
        "outcome": "answered",
        "isolated": isolated,
        "monitor_state": "ISOLATED" if isolated else "NOT-ISOLATED",
        "citations": [{"label": "S1", "filename": filename, "doc_sha256": "c" * 64, "chunk_sha256": "d" * 64}],
        "net": {"ignored": True},
        "policy": {"ignored": True},
    }


def test_report_signature_verifies_and_detects_edits() -> None:
    key = Ed25519PrivateKey.generate()

    def sign(digest: bytes) -> str:
        return base64.b64encode(key.sign(digest)).decode()

    report = build_report([block(1, True, "policy.docx"), block(2, True, "syllabus.pdf")], "demo", "kid", sign)

    body = {k: v for k, v in report.items() if k not in ("report_sha256", "signature")}
    digest = hashlib.sha256(canonical_json(body)).digest()
    assert report["report_sha256"] == digest.hex()
    key.public_key().verify(base64.b64decode(report["signature"]), digest)  # raises if forged

    edited = {**body, "summary": {**body["summary"], "all_isolated": False}}
    assert hashlib.sha256(canonical_json(edited)).digest() != digest


def test_report_summary_and_fields() -> None:
    report = build_report(
        [block(1, True, "policy.docx"), block(2, False, "syllabus.pdf")],
        "demo",
        "kid",
        lambda d: "sig",
    )
    assert report["type"] == REPORT_TYPE
    assert report["summary"]["answers"] == 2
    assert report["summary"]["all_isolated"] is False
    assert report["summary"]["documents"] == ["policy.docx", "syllabus.pdf"]
    assert "net" not in report["answers"][0] and "policy" not in report["answers"][0]


def test_empty_report_is_not_claimed_isolated() -> None:
    report = build_report([], "demo", "kid", lambda d: "sig")
    assert report["summary"]["all_isolated"] is False
