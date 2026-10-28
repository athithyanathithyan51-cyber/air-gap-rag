"""Signed report of the answers a user received, with their isolation records.

The report is canonical JSON. Its SHA-256 is signed with the attestation key, so anyone holding
the public key (GET /api/attestation/pubkey) can check that the report was not edited.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from attestation.verify_chain import canonical_json

REPORT_TYPE = "offline-assistant-attestation-report"
REPORT_VERSION = 1


def _answer(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": block["index"],
        "ts_utc": block["ts_utc"],
        "block_hash": block["block_hash"],
        "query_hash": block["query_hash"],
        "answer_hash": block["answer_hash"],
        "outcome": block["outcome"],
        "isolated": bool(block["isolated"]),
        "monitor_state": block["monitor_state"],
        "citations": block["citations"],
    }


def build_report(
    blocks: list[dict[str, Any]],
    generated_by: str,
    key_id: str,
    sign: Callable[[bytes], str],
) -> dict[str, Any]:
    answers = [_answer(b) for b in blocks]
    body: dict[str, Any] = {
        "type": REPORT_TYPE,
        "version": REPORT_VERSION,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "generated_by": generated_by,
        "key_id": key_id,
        "summary": {
            "answers": len(answers),
            "all_isolated": bool(answers) and all(a["isolated"] for a in answers),
            "documents": sorted({c["filename"] for a in answers for c in a["citations"]}),
        },
        "answers": answers,
    }
    digest = hashlib.sha256(canonical_json(body)).digest()
    return {**body, "report_sha256": digest.hex(), "signature": sign(digest)}
