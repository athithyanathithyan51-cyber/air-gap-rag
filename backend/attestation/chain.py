"""Builds, signs and stores attestation blocks (one per answer)."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from attestation.monitor import IsolationMonitor
from attestation.verify_chain import (
    GENESIS_PREV,
    SCHEMA_VERSION,
    Report,
    canonical_json,
    compute_block_hash,
    evaluate_isolation,
    key_id,
    verify_blocks,
)
from db.models import KV, AttestationBlock

COUNTER_KEY = "attestation_counter"


def sha256_text(text: str) -> str:
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()


class Attestor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        private_key: Ed25519PrivateKey,
        monitor: IsolationMonitor,
        snapshotter: Callable[[], dict[str, Any]],
    ) -> None:
        self._sf = session_factory
        self._key = private_key
        self.public_key = private_key.public_key()
        self.key_id = key_id(self.public_key)
        self.monitor = monitor
        self._snap = snapshotter
        self._lock = threading.Lock()

    def append(
        self,
        username: str,
        question: str,
        chunk_hashes: list[str],
        answer: str,
        citations: list[dict[str, Any]],
        outcome: str,
    ) -> dict[str, Any]:
        """Take a fresh snapshot, build, sign and persist the next block. Thread-safe."""
        net = self._snap()
        policy = self.monitor.policy
        isolated, _ = evaluate_isolation(net, policy)
        if not isolated:
            # Make sure the latch is set even if the monitor thread has not polled yet.
            self.monitor.check_once()
        with self._lock, self._sf() as s:
            last = s.scalar(select(AttestationBlock).order_by(AttestationBlock.index.desc()).limit(1))
            counter_row = s.get(KV, COUNTER_KEY)
            counter = int(counter_row.value) + 1 if counter_row else 0
            block: dict[str, Any] = {
                "v": SCHEMA_VERSION,
                "index": (last.index + 1) if last else 0,
                "ts_utc": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "counter": counter,
                "query_hash": sha256_text(question),
                "chunk_hashes": chunk_hashes,
                "answer_hash": sha256_text(answer),
                "outcome": outcome,
                "citations": citations,
                "net": net,
                "policy": policy,
                "isolated": isolated,
                "monitor_state": self.monitor.state,
                "prev_hash": last.block_hash if last else GENESIS_PREV,
                "key_id": self.key_id,
            }
            block["block_hash"] = compute_block_hash(block)
            block["sig"] = base64.b64encode(self._key.sign(bytes.fromhex(block["block_hash"]))).decode()
            s.add(
                AttestationBlock(
                    index=block["index"],
                    block_hash=block["block_hash"],
                    body=canonical_json(block).decode(),
                    username=username,
                )
            )
            if counter_row is None:
                s.add(KV(key=COUNTER_KEY, value=str(counter)))
            else:
                counter_row.value = str(counter)
            s.commit()
        return block

    def blocks(self, upto: int | None = None) -> list[dict[str, Any]]:
        with self._sf() as s:
            q = select(AttestationBlock).order_by(AttestationBlock.index)
            if upto is not None:
                q = q.where(AttestationBlock.index <= upto)
            return [json.loads(b.body) for b in s.scalars(q).all()]

    def get(self, index: int) -> tuple[dict[str, Any], str] | None:
        with self._sf() as s:
            row = s.get(AttestationBlock, index)
            return (json.loads(row.body), row.username) if row else None

    def count(self) -> int:
        with self._sf() as s:
            return int(s.scalar(select(func.count()).select_from(AttestationBlock)) or 0)

    def verify(self, upto: int | None = None) -> Report:
        return verify_blocks(self.blocks(upto), self.public_key)

    def export_jsonl(self) -> str:
        return "".join(canonical_json(b).decode() + "\n" for b in self.blocks())
