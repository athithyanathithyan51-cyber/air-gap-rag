"""User management and audit log (admin only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.auth_routes import user_out
from api.deps import AdminDep, CsrfDep, SessionDep
from auth.security import ROLES, hash_password
from db.audit import audit
from db.models import AuditEvent, RefreshToken, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=256)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserPatch(BaseModel):
    active: bool | None = None
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    password: str | None = Field(default=None, min_length=10, max_length=256)


@router.get("/users")
def list_users(_: AdminDep, s: SessionDep) -> list[dict[str, Any]]:
    return [{**user_out(u), "active": u.active} for u in s.scalars(select(User).order_by(User.username)).all()]


@router.post("/users", dependencies=[CsrfDep], status_code=status.HTTP_201_CREATED)
def create_user(body: UserIn, admin: AdminDep, s: SessionDep) -> dict[str, Any]:
    name = body.username.lower()
    if s.scalar(select(User).where(User.username == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")
    user = User(username=name, password_hash=hash_password(body.password), role=body.role)
    s.add(user)
    s.commit()
    audit(s, admin.username, "user.create", username=name, role=body.role)
    return {**user_out(user), "active": user.active}


@router.patch("/users/{user_id}", dependencies=[CsrfDep])
def update_user(user_id: int, body: UserPatch, admin: AdminDep, s: SessionDep) -> dict[str, Any]:
    user = s.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if user.id == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "you cannot disable or demote yourself")
    changes: dict[str, Any] = {}
    if body.active is not None:
        user.active = body.active
        changes["active"] = body.active
    if body.role is not None:
        assert body.role in ROLES
        user.role = body.role
        changes["role"] = body.role
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        changes["password_reset"] = True
    if body.active is False or body.password is not None:
        for t in s.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)).all():
            t.revoked = True
    s.commit()
    audit(s, admin.username, "user.update", username=user.username, **changes)
    return {**user_out(user), "active": user.active}


@router.get("/audit")
def audit_log(
    _: AdminDep,
    s: SessionDep,
    limit: int = Query(default=100, ge=1, le=1000),
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if before_id is not None:
        q = q.where(AuditEvent.id < before_id)
    return [
        {"id": e.id, "ts": e.ts.isoformat(), "actor": e.actor, "action": e.action, "detail": e.detail}
        for e in s.scalars(q).all()
    ]
