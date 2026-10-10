"""Append-only audit log helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from db.models import AuditEvent

log = logging.getLogger("airgap.audit")


def audit(session: Session, actor: str, action: str, **detail: Any) -> None:
    session.add(AuditEvent(actor=actor, action=action, detail=detail))
    session.commit()
    log.info("audit", extra={"actor": actor, "action": action, "detail": detail})
