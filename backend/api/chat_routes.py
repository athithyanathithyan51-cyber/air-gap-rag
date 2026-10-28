"""Question answering over Server-Sent Events, with one attestation block per answer."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import CsrfDep, SessionDep, SvcDep, UserDep, rate_limited
from db.audit import audit
from rag.answer import AnswerEngine, Source, Verdict
from rag.ollama import LLMUnavailableError

log = logging.getLogger("airgap.chat")
router = APIRouter(prefix="/api", tags=["chat"])


class ChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    document_id: int | None = Field(default=None, ge=1)  # limit retrieval to one document


def sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


def citation_record(src: Source) -> dict[str, Any]:
    return {
        "label": src.label,
        "document_id": src.document_id,
        "filename": src.filename,
        "doc_sha256": src.doc_sha256,
        "page": src.page,
        "section": src.section,
        "chunk_id": src.chunk_id,
        "chunk_sha256": src.chunk_sha256,
    }


@router.post("/chat", dependencies=[CsrfDep, rate_limited("chat", "chat_rate_limit")])
async def chat(body: ChatIn, user: UserDep, svc: SvcDep, s: SessionDep) -> StreamingResponse:
    st = svc.settings
    engine = AnswerEngine(
        s,
        svc.store,
        svc.embedder,
        svc.llm,
        st.top_k,
        st.min_score,
        max_context_chars=st.max_context_chars,
        general_chat=st.general_chat,
    )
    username = user.username

    async def events() -> AsyncIterator[bytes]:
        try:
            async for ev in engine.stream(body.question, body.document_id):
                if ev["type"] != "final":
                    yield sse(ev)
                    continue
                verdict: Verdict = ev["verdict"]
                sources: list[Source] = ev["sources"]
                block = svc.attestor.append(
                    username=username,
                    question=body.question,
                    chunk_hashes=[src.chunk_sha256 for src in sources],
                    answer=verdict.answer,
                    citations=[citation_record(c) for c in verdict.cited],
                    outcome=f"{verdict.status}:{verdict.reason}",
                )
                audit(
                    s,
                    username,
                    "chat.answer",
                    status=verdict.status,
                    reason=verdict.reason,
                    attestation_index=block["index"],
                    query_hash=block["query_hash"],
                )
                yield sse(
                    {
                        "type": "final",
                        "status": verdict.status,
                        "reason": verdict.reason,
                        "answer": verdict.answer,
                        "citations": [c.public(include_text=False) for c in verdict.cited],
                        "support": round(verdict.support, 3),
                        "best_score": round(float(ev["best_score"]), 4),
                        "attestation": {
                            "index": block["index"],
                            "block_hash": block["block_hash"],
                            "isolated": block["isolated"],
                            "monitor_state": block["monitor_state"],
                        },
                    }
                )
        except LLMUnavailableError as exc:
            log.warning("llm_unavailable", extra={"error": str(exc)})
            yield sse(
                {"type": "error", "message": "The local language model is unavailable. Ask an admin to check Ollama."}
            )
        except Exception:
            log.exception("chat_failed")
            yield sse({"type": "error", "message": "Internal error while answering."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
