"""Shared service container and FastAPI dependencies."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings
from attestation.chain import Attestor
from attestation.monitor import IsolationMonitor
from auth.security import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, AuthError, TokenService, csrf_ok
from db.models import User
from db.session import Database
from rag.ollama import ChatModel, Embedder
from rag.vectors import VectorStore


class RateLimiter:
    """In-memory sliding window, keyed by (bucket, client). Single-process deployment."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def parse(rule: str) -> tuple[int, float]:
        count, _, period = rule.partition("/")
        seconds = {"second": 1.0, "minute": 60.0, "hour": 3600.0}[period.strip()]
        return int(count), seconds

    def hit(self, bucket: str, key: str, rule: str) -> bool:
        limit, window = self.parse(rule)
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


@dataclass
class Services:
    settings: Settings
    db: Database
    store: VectorStore
    embedder: Embedder
    llm: ChatModel
    tokens: TokenService
    monitor: IsolationMonitor
    attestor: Attestor
    limiter: RateLimiter


def services(request: Request) -> Services:
    svc: Services = request.app.state.services
    return svc


def db_session(svc: Annotated[Services, Depends(services)]) -> Iterator[Session]:
    with svc.db.session() as s:
        yield s


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_user(
    request: Request,
    svc: Annotated[Services, Depends(services)],
    s: Annotated[Session, Depends(db_session)],
) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    try:
        claims = svc.tokens.decode_access(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = s.get(User, int(claims["sub"]))
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account disabled")
    return user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return user


def require_csrf(request: Request) -> None:
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")


def rate_limited(bucket: str, rule_attr: str) -> Any:
    def dep(request: Request, svc: Annotated[Services, Depends(services)]) -> None:
        rule = getattr(svc.settings, rule_attr)
        if not svc.limiter.hit(bucket, client_key(request), rule):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded; try again shortly")

    return Depends(dep)


SvcDep = Annotated[Services, Depends(services)]
SessionDep = Annotated[Session, Depends(db_session)]
UserDep = Annotated[User, Depends(current_user)]
AdminDep = Annotated[User, Depends(require_admin)]
CsrfDep = Depends(require_csrf)
