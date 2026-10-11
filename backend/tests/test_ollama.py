from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.main import warm_up_models
from rag.ollama import OllamaClient


def client_with(handler: Any) -> OllamaClient:
    c = OllamaClient("http://127.0.0.1:11434", "chat-model", "embed-model", num_ctx=4096, num_predict=256)
    transport = httpx.MockTransport(handler)
    c._client = lambda: httpx.AsyncClient(base_url=c.base_url, transport=transport)  # type: ignore[method-assign]
    return c


async def test_chat_payload_caps_context_and_answer_length() -> None:
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        lines = [{"message": {"content": "Hi"}, "done": False}, {"message": {"content": ""}, "done": True}]
        return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))

    out = [p async for p in client_with(handler).stream_chat([{"role": "user", "content": "hi"}])]
    assert out == ["Hi"]
    assert seen["options"]["num_ctx"] == 4096
    assert seen["options"]["num_predict"] == 256


async def test_warm_up_loads_chat_and_embedding_models() -> None:
    paths: list[tuple[str, str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        paths.append((req.url.path, body["model"]))
        if req.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.0, 1.0]]})
        assert body["keep_alive"] == "30m"
        return httpx.Response(200, json={"done": True})

    await client_with(handler).warm_up()
    assert paths == [("/api/generate", "chat-model"), ("/api/embed", "embed-model")]


async def test_warm_up_failure_never_breaks_startup(caplog: pytest.LogCaptureFixture) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model not found")

    await warm_up_models(client_with(handler))  # must not raise
    assert any(r.message == "model_warm_up_failed" for r in caplog.records)


async def test_warm_up_skipped_for_models_without_it() -> None:
    await warm_up_models(object())
