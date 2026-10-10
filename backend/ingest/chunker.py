"""Structure-aware chunking.

Chunks never cross a page or section boundary, so every chunk has exactly one
citation location. Within a segment, text is packed paragraph by paragraph up
to the token budget with an overlap carried into the next chunk.

Token counts are estimated as ceil(chars / 4), which is close to the
nomic/Qwen tokenizers for English prose; it avoids shipping a tokenizer that
might try to download vocab files at runtime.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from ingest.parsers import Segment

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


@dataclass(frozen=True)
class ChunkData:
    ordinal: int
    text: str
    page: int | None
    section: str | None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    cur = ""
    for sentence in _SENTENCE.split(paragraph):
        while len(sentence) > max_chars:  # a single enormous "sentence" (tables, code)
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if cur and len(cur) + 1 + len(sentence) > max_chars:
            pieces.append(cur)
            cur = sentence
        else:
            cur = f"{cur} {sentence}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def _tail(text: str, max_chars: int) -> str:
    if max_chars <= 0 or not text:
        return ""
    tail = text[-max_chars:]
    cut = tail.find(" ")
    return tail[cut + 1 :] if 0 <= cut < len(tail) - 1 else tail


def chunk_segments(segments: list[Segment], chunk_tokens: int = 800, overlap_tokens: int = 100) -> list[ChunkData]:
    if overlap_tokens >= chunk_tokens:
        raise ValueError("overlap must be smaller than chunk size")
    max_chars = chunk_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    out: list[ChunkData] = []
    seen: set[str] = set()

    def emit(text: str, seg: Segment) -> None:
        text = text.strip()
        if not text:
            return
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in seen:  # identical boilerplate (headers/footers) indexed once
            return
        seen.add(digest)
        out.append(ChunkData(ordinal=len(out), text=text, page=seg.page, section=seg.section))

    for seg in segments:
        paragraphs = [p.strip() for p in seg.text.split("\n\n") if p.strip()]
        pieces = [piece for p in paragraphs for piece in _split_long(p, max_chars - overlap_chars)]
        cur = ""
        for piece in pieces:
            if cur and len(cur) + 2 + len(piece) > max_chars:
                emit(cur, seg)
                cur = _tail(cur, overlap_chars)
                cur = f"{cur}\n\n{piece}" if cur else piece
            else:
                cur = f"{cur}\n\n{piece}" if cur else piece
        emit(cur, seg)
    return out
