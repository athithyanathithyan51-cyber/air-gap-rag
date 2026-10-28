"""Document upload (admin), listing, deletion and citation lookup."""

from __future__ import annotations

import errno
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from api.deps import AdminDep, CsrfDep, SessionDep, SvcDep, UserDep
from db.models import Chunk, Document
from ingest.pipeline import Ingestor, UploadRejectedError
from rag.ollama import LLMUnavailableError

router = APIRouter(prefix="/api/documents", tags=["documents"])


def doc_out(d: Document) -> dict[str, Any]:
    return {
        "id": d.id,
        "filename": d.filename,
        "sha256": d.sha256,
        "mime": d.mime,
        "size_bytes": d.size_bytes,
        "pages": d.pages,
        "chunk_count": d.chunk_count,
        "status": d.status,
        "error": d.error,
        "uploaded_by": d.uploaded_by,
        "created_at": d.created_at.isoformat(),
    }


def make_ingestor(svc: SvcDep, s: SessionDep) -> Ingestor:
    st = svc.settings
    return Ingestor(
        s,
        svc.store,
        svc.embedder,
        st.docs_dir,
        st.chunk_tokens,
        st.chunk_overlap_tokens,
        st.max_upload_mb * 1024 * 1024,
        st.max_pdf_pages,
    )


@router.get("")
def list_documents(_: UserDep, s: SessionDep) -> list[dict[str, Any]]:
    return [doc_out(d) for d in s.scalars(select(Document).order_by(Document.filename)).all()]


@router.post("", dependencies=[CsrfDep], status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, admin: AdminDep, svc: SvcDep, s: SessionDep) -> dict[str, Any]:
    limit = svc.settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file exceeds {svc.settings.max_upload_mb} MB")
    try:
        result = await make_ingestor(svc, s).ingest(data, file.filename or "document", admin.username)
    except UploadRejectedError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except LLMUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"embedding model unavailable: {exc}") from exc
    except (OSError, sqlite3.OperationalError) as exc:
        if getattr(exc, "errno", None) == errno.ENOSPC or "disk is full" in str(exc):
            detail = "disk is full: free space, then upload again"
            raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, detail) from exc
        raise
    return {"outcome": result.outcome, "document": doc_out(result.document)}


@router.delete("/{doc_id}", dependencies=[CsrfDep])
def delete(doc_id: int, admin: AdminDep, svc: SvcDep, s: SessionDep) -> dict[str, str]:
    doc = s.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    make_ingestor(svc, s).remove(doc, admin.username)
    return {"status": "deleted"}


@router.get("/chunks/{chunk_id}")
def get_chunk(chunk_id: int, _: UserDep, s: SessionDep) -> dict[str, Any]:
    chunk = s.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "chunk not found (document may have been removed)")
    d = chunk.document
    return {
        "chunk_id": chunk.id,
        "document_id": d.id,
        "filename": d.filename,
        "page": chunk.page,
        "section": chunk.section,
        "text": chunk.text,
        "sha256": chunk.sha256,
    }


@router.get("/{doc_id}/file")
def download(doc_id: int, _: UserDep, svc: SvcDep, s: SessionDep) -> Response:
    doc = s.get(Document, doc_id)
    path = svc.settings.docs_dir / doc.sha256 if doc else None
    if doc is None or path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    safe = doc.filename.replace('"', "")
    return Response(
        path.read_bytes(),
        media_type=doc.mime,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )
