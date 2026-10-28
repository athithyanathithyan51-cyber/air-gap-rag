"""Attestation: per-answer verification, chain export, monitor status, acknowledgement."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

from api.deps import AdminDep, CsrfDep, SvcDep, UserDep
from attestation.keys import public_pem
from attestation.report import build_report
from attestation.verify_chain import evaluate_isolation

router = APIRouter(prefix="/api/attestation", tags=["attestation"])

LIMITS = [
    "This is a tamper-evident record of network-interface state at the moment of each answer.",
    "It is not proof that no packet was ever sent; packet captures are the separate evidence for that.",
    "Tamper-evident, not tamper-proof: someone with host access and the signing key can forge a new chain.",
    "A snapshot shows interface state at one moment, not all traffic between snapshots.",
    "Changing the system clock changes timestamps; the monotonic counter and hash links preserve order.",
]


@router.get("/status")
def monitor_status(_: UserDep, svc: SvcDep) -> dict[str, Any]:
    return {**svc.monitor.status(), "blocks": svc.attestor.count(), "key_id": svc.attestor.key_id, "limits": LIMITS}


@router.get("/blocks/{index}")
def verify_block(index: int, user: UserDep, svc: SvcDep) -> dict[str, Any]:
    found = svc.attestor.get(index)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "block not found")
    block, owner = found
    if user.role != "admin" and owner != user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can only verify your own answers")
    report = svc.attestor.verify(upto=index)
    _, reasons = evaluate_isolation(block["net"], block["policy"])
    return {
        "block": block,
        "chain_valid_up_to_block": report.valid,
        "chain_report": report.as_dict(),
        "isolated": block["isolated"] and block["monitor_state"] == "ISOLATED",
        "isolation_reasons": reasons,
        "limits": LIMITS,
    }


MAX_REPORT_ANSWERS = 200


@router.get("/report")
def signed_report(indexes: str, user: UserDep, svc: SvcDep) -> dict[str, Any]:
    """Signed report of the chosen answers. Users can include only their own answers; admins any."""
    try:
        wanted = sorted({int(x) for x in indexes.split(",") if x.strip()})
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "indexes must be numbers separated by commas") from exc
    if not 1 <= len(wanted) <= MAX_REPORT_ANSWERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"choose between 1 and {MAX_REPORT_ANSWERS} answers")
    blocks: list[dict[str, Any]] = []
    for index in wanted:
        found = svc.attestor.get(index)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"answer record {index} not found")
        block, owner = found
        if user.role != "admin" and owner != user.username:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "you can only export your own answers")
        blocks.append(block)
    return build_report(blocks, user.username, svc.attestor.key_id, svc.attestor.sign_digest)


@router.get("/export", response_class=PlainTextResponse)
def export_chain(_: AdminDep, svc: SvcDep) -> PlainTextResponse:
    return PlainTextResponse(
        svc.attestor.export_jsonl(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="attestation-chain.jsonl"'},
    )


@router.get("/pubkey", response_class=PlainTextResponse)
def pubkey(_: UserDep, svc: SvcDep) -> PlainTextResponse:
    return PlainTextResponse(
        public_pem(svc.attestor.public_key).decode(),
        headers={"Content-Disposition": 'attachment; filename="attestation.pub"'},
    )


@router.get("/verify")
def verify_all(_: AdminDep, svc: SvcDep) -> dict[str, Any]:
    return svc.attestor.verify().as_dict()


@router.post("/acknowledge", dependencies=[CsrfDep])
def acknowledge(admin: AdminDep, svc: SvcDep) -> dict[str, Any]:
    try:
        return svc.monitor.acknowledge(admin.username)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
