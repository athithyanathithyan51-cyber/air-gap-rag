"""Ingestion pipeline: sniff -> parse -> chunk -> store -> embed -> index.

- Dedup: a file whose SHA-256 is already ingested is not processed again.
- Incremental re-ingest: uploading a changed file with the same filename
  replaces the old version (its chunks and vectors are removed).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.audit import audit
from db.models import Chunk, Document
from ingest.chunker import chunk_segments
from ingest.parsers import ParseError, UnsupportedFileError, parse
from rag.ollama import Embedder
from rag.vectors import VectorStore

log = logging.getLogger("airgap.ingest")


class UploadRejectedError(ValueError):
    pass


@dataclass(frozen=True)
class IngestResult:
    document: Document
    outcome: str  # ingested | duplicate | replaced | failed


def _safe_name(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name.strip() or "document"
    return "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')[:255]


class Ingestor:
    def __init__(
        self,
        session: Session,
        store: VectorStore,
        embedder: Embedder,
        docs_dir: Path,
        chunk_tokens: int = 800,
        overlap_tokens: int = 100,
        max_bytes: int = 50 * 1024 * 1024,
        max_pdf_pages: int = 2000,
    ) -> None:
        self.s = session
        self.store = store
        self.embedder = embedder
        self.docs_dir = docs_dir
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.max_bytes = max_bytes
        self.max_pdf_pages = max_pdf_pages

    def remove(self, doc: Document, actor: str) -> None:
        self.store.delete_document(doc.id)
        stored = self.docs_dir / doc.sha256
        stored.unlink(missing_ok=True)
        audit(self.s, actor, "document.delete", document_id=doc.id, filename=doc.filename, sha256=doc.sha256)
        self.s.delete(doc)
        self.s.commit()

    async def ingest(self, data: bytes, filename: str, actor: str) -> IngestResult:
        filename = _safe_name(filename)
        if len(data) == 0:
            raise UploadRejectedError("empty file")
        if len(data) > self.max_bytes:
            raise UploadRejectedError(f"file exceeds {self.max_bytes // (1024 * 1024)} MB limit")
        digest = hashlib.sha256(data).hexdigest()

        existing = self.s.scalar(select(Document).where(Document.sha256 == digest))
        if existing is not None and existing.status == "ready":
            audit(self.s, actor, "document.duplicate", document_id=existing.id, filename=filename)
            return IngestResult(existing, "duplicate")
        if existing is not None:  # an earlier failed attempt: retry from scratch
            self.store.delete_document(existing.id)
            self.s.delete(existing)
            self.s.commit()

        try:
            mime, segments, pages = parse(data, filename, self.max_pdf_pages)
        except (UnsupportedFileError, ParseError) as exc:
            audit(self.s, actor, "document.rejected", filename=filename, sha256=digest, error=str(exc)[:500])
            raise UploadRejectedError(str(exc)) from exc

        replaced = False
        for old in self.s.scalars(select(Document).where(Document.filename == filename)).all():
            self.remove(old, actor)
            replaced = True

        doc = Document(
            filename=filename, sha256=digest, mime=mime, size_bytes=len(data), pages=pages, uploaded_by=actor
        )
        self.s.add(doc)
        self.s.commit()
        try:
            chunks = chunk_segments(segments, self.chunk_tokens, self.overlap_tokens)
            if not chunks:
                raise ParseError("no text chunks produced")
            rows = [
                Chunk(
                    document_id=doc.id, ordinal=c.ordinal, page=c.page, section=c.section, text=c.text, sha256=c.sha256
                )
                for c in chunks
            ]
            self.s.add_all(rows)
            self.s.flush()
            vectors = await self.embedder.embed_documents([c.text for c in chunks])
            self.store.ensure_collection()
            self.store.upsert(
                [
                    (row.id, vec, {"document_id": doc.id, "page": row.page, "section": row.section})
                    for row, vec in zip(rows, vectors, strict=True)
                ]
            )
            doc.chunk_count = len(rows)
            doc.status = "ready"
            self.s.commit()
            self.docs_dir.mkdir(parents=True, exist_ok=True)
            (self.docs_dir / digest).write_bytes(data)
        except Exception as exc:
            self.s.rollback()
            doc.status = "failed"
            doc.error = str(exc)[:1000]
            self.s.add(doc)
            self.s.commit()
            self.store.delete_document(doc.id)
            audit(self.s, actor, "document.failed", document_id=doc.id, filename=filename, error=doc.error)
            log.warning("ingest_failed", extra={"filename": filename, "error": doc.error})
            if isinstance(exc, ParseError):
                return IngestResult(doc, "failed")
            raise
        outcome = "replaced" if replaced else "ingested"
        audit(
            self.s,
            actor,
            f"document.{outcome}",
            document_id=doc.id,
            filename=filename,
            sha256=digest,
            chunks=doc.chunk_count,
            pages=pages,
        )
        return IngestResult(doc, outcome)
