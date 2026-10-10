"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import admin_routes, attestation_routes, auth_routes, chat_routes, document_routes
from api.deps import Services
from app.config import Settings, get_settings
from app.logging import configure_logging
from app.net_guard import install_guard

log = logging.getLogger("airgap.app")

APP_VERSION = "0.1.0"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


ReadinessCheck = Callable[[], Awaitable[CheckResult]]


def default_checks(settings: Settings) -> list[ReadinessCheck]:
    async def qdrant() -> CheckResult:
        try:
            async with httpx.AsyncClient(timeout=settings.ready_timeout_s, trust_env=False) as c:
                r = await c.get(f"{settings.qdrant_url}/readyz")
            return CheckResult("qdrant", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001 - readiness reports any failure
            return CheckResult("qdrant", False, type(exc).__name__)

    async def ollama() -> CheckResult:
        try:
            async with httpx.AsyncClient(timeout=settings.ready_timeout_s, trust_env=False) as c:
                r = await c.get(f"{settings.ollama_url}/api/tags")
            if r.status_code != 200:
                return CheckResult("ollama", False, f"HTTP {r.status_code}")
            names = {m.get("name", "") for m in r.json().get("models", [])}
            wanted = {settings.chat_model, settings.embed_model}
            missing = sorted(w for w in wanted if not any(n == w or n.startswith(w + ":") for n in names))
            if missing:
                return CheckResult("ollama", False, "missing models: " + ", ".join(missing))
            return CheckResult("ollama", True, "models present")
        except Exception as exc:  # noqa: BLE001
            return CheckResult("ollama", False, type(exc).__name__)

    return [qdrant, ollama]


def _service_hosts(settings: Settings) -> list[str]:
    hosts = []
    for url in (settings.qdrant_url, settings.ollama_url):
        host = urlparse(url).hostname
        if host:
            hosts.append(host)
    return hosts


def create_app(
    settings: Settings | None = None,
    readiness_checks: Sequence[ReadinessCheck] | None = None,
    frontend_dist: Path | None = None,
    services: Services | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    checks = list(readiness_checks) if readiness_checks is not None else default_checks(settings)
    if services is None:
        from app.services import build_services

        services = build_services(settings)
    svc = services

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            settings.log_level,
            settings.log_dir if settings.environment != "test" else None,
            settings.log_max_bytes,
            settings.log_backup_count,
        )
        if settings.net_guard_enabled:
            install_guard([*settings.net_allowed_hosts, *_service_hosts(settings)])
        if settings.monitor_enabled:
            svc.monitor.start()
        log.info("startup", extra={"version": APP_VERSION, "environment": settings.environment})
        yield
        svc.monitor.stop()
        log.info("shutdown")

    # Swagger/ReDoc pages load JS from public CDNs, so they are disabled entirely.
    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment == "development" else None,
        lifespan=lifespan,
    )

    app.state.services = svc
    for r in (auth_routes, document_routes, chat_routes, attestation_routes, admin_routes):
        app.include_router(r.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.url.path.startswith("/api/") or request.url.path in ("/health", "/ready"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/ready", tags=["ops"])
    async def ready() -> JSONResponse:
        results = [await check() for check in checks]
        ok = all(r.ok for r in results)
        body = {
            "status": "ready" if ok else "not_ready",
            "checks": {r.name: {"ok": r.ok, "detail": r.detail} for r in results},
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    dist = frontend_dist if frontend_dist is not None else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.bind_host,
        port=settings.bind_port,
        log_config=None,
        server_header=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    run()
