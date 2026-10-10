"""Passwords (argon2id), JWT access tokens, rotating refresh tokens, CSRF tokens.

Session model:
- access token: JWT (HS256), 15 min, in an httpOnly SameSite=Strict cookie.
- refresh token: random 256-bit value, 7 days, httpOnly cookie scoped to /api/auth.
  Only its SHA-256 is stored. Each use rotates it; reusing an already-used token
  revokes the whole token family (stolen-token detection).
- CSRF: double-submit token. A non-httpOnly cookie `airgap_csrf` must be echoed
  in the X-CSRF-Token header on every state-changing request.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db.models import RefreshToken, User

ACCESS_COOKIE = "airgap_access"
REFRESH_COOKIE = "airgap_refresh"
CSRF_COOKIE = "airgap_csrf"
CSRF_HEADER = "X-CSRF-Token"

_hasher = PasswordHasher()  # argon2id with library-recommended parameters
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

ROLES = ("admin", "user")


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    if len(password) > 256:
        raise ValueError("password too long")


def verify_password(user: User | None, password: str) -> bool:
    if user is None:
        # Equalise timing so usernames cannot be probed.
        with contextlib.suppress(VerificationError):
            _hasher.verify(_DUMMY_HASH, password)
        return False
    try:
        return _hasher.verify(user.password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def load_or_create_secret(path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = secrets.token_bytes(64)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return data


class TokenService:
    def __init__(self, secret: bytes, access_minutes: int = 15, refresh_days: int = 7) -> None:
        self.secret = secret
        self.access_ttl = timedelta(minutes=access_minutes)
        self.refresh_ttl = timedelta(days=refresh_days)

    def issue_access(self, user: User) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(user.id),
            "usr": user.username,
            "role": user.role,
            "iat": int(now.timestamp()),
            "exp": int((now + self.access_ttl).timestamp()),
            "jti": secrets.token_hex(8),
        }
        return jwt.encode(claims, self.secret, algorithm="HS256")

    def decode_access(self, token: str) -> dict[str, Any]:
        try:
            return dict(jwt.decode(token, self.secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}))
        except jwt.PyJWTError as exc:
            raise AuthError("invalid or expired session") from exc

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue_refresh(self, s: Session, user: User, family: str | None = None) -> str:
        token = secrets.token_urlsafe(32)
        s.add(
            RefreshToken(
                user_id=user.id,
                token_hash=self._digest(token),
                family=family or secrets.token_hex(16),
                expires_at=datetime.now(UTC) + self.refresh_ttl,
            )
        )
        s.commit()
        return token

    def rotate_refresh(self, s: Session, token: str) -> tuple[User, str]:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == self._digest(token)))
        if row is None or row.revoked:
            raise AuthError("invalid refresh token")
        if row.used:
            # Reuse of a rotated token: assume theft, kill the whole family.
            s.execute(update(RefreshToken).where(RefreshToken.family == row.family).values(revoked=True))
            s.commit()
            raise AuthError("refresh token reuse detected; all sessions in this family revoked")
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            raise AuthError("refresh token expired")
        user = s.get(User, row.user_id)
        if user is None or not user.active:
            raise AuthError("account disabled")
        row.used = True
        s.commit()
        return user, self.issue_refresh(s, user, row.family)

    def revoke_refresh(self, s: Session, token: str) -> None:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == self._digest(token)))
        if row is not None:
            s.execute(update(RefreshToken).where(RefreshToken.family == row.family).values(revoked=True))
            s.commit()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(cookie: str | None, header: str | None) -> bool:
    return bool(cookie) and bool(header) and hmac.compare_digest(str(cookie), str(header))
