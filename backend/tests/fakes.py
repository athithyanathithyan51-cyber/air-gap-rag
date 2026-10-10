"""Test doubles: deterministic embedder, scripted LLM, fake network snapshots, tiny PDF writer."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import AsyncIterator
from typing import Any

DIM = 768
_WORD = re.compile(r"[a-z0-9]+")


def bow_vector(text: str) -> list[float]:
    vec = [0.0] * DIM
    for w in _WORD.findall(text.lower()):
        if len(w) < 3:
            continue
        h = int.from_bytes(hashlib.sha256(w.encode()).digest()[:4], "big")
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [bow_vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return bow_vector(text)


class FakeLLM:
    """Yields `reply` in small pieces; records the messages it was given."""

    def __init__(self, reply: str = "I don't know.") -> None:
        self.reply = reply
        self.messages: list[dict[str, str]] = []

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.messages = messages
        for i in range(0, len(self.reply), 7):
            yield self.reply[i : i + 7]


ISOLATED_NET: dict[str, Any] = {
    "platform": "linux",
    "interfaces": [
        {"name": "docker0", "up": True, "addrs": ["172.17.0.1"], "kind": "container-bridge"},
        {"name": "eth0", "up": False, "addrs": [], "kind": "physical"},
    ],
    "default_route_v4": False,
    "default_route_v6": False,
}

CONNECTED_NET: dict[str, Any] = {
    "platform": "linux",
    "interfaces": [
        {"name": "docker0", "up": True, "addrs": ["172.17.0.1"], "kind": "container-bridge"},
        {"name": "eth0", "up": True, "addrs": ["192.168.1.20"], "kind": "physical"},
    ],
    "default_route_v4": True,
    "default_route_v6": False,
}


class SwitchableNet:
    def __init__(self) -> None:
        self.current: dict[str, Any] = ISOLATED_NET

    def __call__(self) -> dict[str, Any]:
        return self.current


def make_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF with one Helvetica text line set per page."""
    objs: list[bytes] = []
    n_pages = len(pages)
    font_id = 3 + 2 * n_pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    for i, text in enumerate(pages):
        lines = text.split("\n")
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
        for line in lines:
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({esc}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
