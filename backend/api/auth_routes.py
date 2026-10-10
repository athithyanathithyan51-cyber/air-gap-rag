"""Login, refresh, logout, current user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.deps import CsrfDep, SessionDep, SvcDep, UserDep, client_key, rate_limited
from auth.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    AuthError,
    new_csrf_token,
    verify_password,
)
from db.audit import audit
from db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def user_out(user: User) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "role": user.role}


def _set_session_cookies(response: Response, svc: SvcDep, access: str, refresh: str) -> None:
    secure = svc.settings.cookie_secure
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
        max_age=int(svc.tokens.access_ttl.total_seconds()),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/api/auth",
        max_age=int(svc.tokens.refresh_ttl.total_seconds()),
    )
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), httponly=False, samesite="strict", secure=secure, path="/")


def _clear(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/login", dependencies=[rate_limited("login", "login_rate_limit")])
def login(body: LoginIn, request: Request, response: Response, svc: SvcDep, s: SessionDep) -> dict[str, Any]:
    user = s.scalar(select(User).where(User.username == body.username.strip().lower()))
    if not verify_password(user, body.password) or user is None or not user.active:
        audit(s, body.username[:64], "auth.login_failed", ip=client_key(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    _set_session_cookies(response, svc, svc.tokens.issue_access(user), svc.tokens.issue_refresh(s, user))
    audit(s, user.username, "auth.login", ip=client_key(request))
    return user_out(user)


@router.post("/refresh", dependencies=[rate_limited("refresh", "login_rate_limit")])
def refresh(request: Request, response: Response, svc: SvcDep, s: SessionDep) -> dict[str, Any]:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no refresh token")
    try:
        user, new_refresh = svc.tokens.rotate_refresh(s, token)
    except AuthError as exc:
        _clear(response)
        audit(s, "unknown", "auth.refresh_rejected", reason=str(exc), ip=client_key(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    _set_session_cookies(response, svc, svc.tokens.issue_access(user), new_refresh)
    return user_out(user)


@router.post("/logout", dependencies=[CsrfDep])
def logout(request: Request, response: Response, svc: SvcDep, s: SessionDep) -> dict[str, str]:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        svc.tokens.revoke_refresh(s, token)
    _clear(response)
    return {"status": "signed out"}


@router.get("/me")
def me(user: UserDep) -> dict[str, Any]:
    return user_out(user)
