"""Minimal Ollama client (loopback HTTP only)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

# nomic-embed-text is trained with task prefixes; using them is required for good retrieval.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class LLMUnavailableError(RuntimeError):
    """Ollama is down, the model is missing, or the request timed out."""


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class ChatModel(Protocol):
    def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout_s: float = 300.0,
        temperature: float = 0.1,
        num_ctx: int = 8192,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self._timeout = httpx.Timeout(timeout_s, connect=5.0)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout, trust_env=False)

    async def _embed(self, inputs: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        try:
            async with self._client() as c:
                for i in range(0, len(inputs), 32):
                    r = await c.post("/api/embed", json={"model": self.embed_model, "input": inputs[i : i + 32]})
                    if r.status_code != 200:
                        raise LLMUnavailableError(f"embedding failed: HTTP {r.status_code} {r.text[:200]}")
                    out.extend(r.json()["embeddings"])
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama unreachable: {type(exc).__name__}") from exc
        return out

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed([DOC_PREFIX + t for t in texts])

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([QUERY_PREFIX + text]))[0]

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        try:
            async with self._client() as c, c.stream("POST", "/api/chat", json=payload) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode(errors="replace")[:200]
                    raise LLMUnavailableError(f"chat failed: HTTP {r.status_code} {body}")
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("error"):
                        raise LLMUnavailableError(str(msg["error"]))
                    piece = msg.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if msg.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama unreachable: {type(exc).__name__}") from exc
