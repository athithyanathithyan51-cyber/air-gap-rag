"""Traffic: read-only view of packet captures saved by scripts/capture-windows.ps1 (admin only)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import AdminDep, SvcDep
from traffic.pcap import read_packets, summarize

router = APIRouter(prefix="/api/traffic", tags=["traffic"])

# Capture folders are named by the script in UTC, e.g. 20261028T103446Z. Anything else is refused.
CAPTURE_NAME = re.compile(r"^\d{8}T\d{6}Z$")
PCAP_FILE = "capture.pcapng"
MAX_PAGE = 200


def captures_dir(svc: Any) -> Path:
    return svc.settings.data_dir / "captures"


def capture_path(svc: Any, name: str) -> Path:
    if not CAPTURE_NAME.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown capture name")
    path = captures_dir(svc) / name / PCAP_FILE
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "capture not found")
    return path


def read_verdict(folder: Path) -> str | None:
    verdict = folder / "verdict.txt"
    if not verdict.is_file():
        return None
    for line in verdict.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("VERDICT:"):
            return line.removeprefix("VERDICT:").strip()
    return None


@router.get("/captures")
def list_captures(_: AdminDep, svc: SvcDep) -> list[dict[str, Any]]:
    root = captures_dir(svc)
    if not root.is_dir():
        return []
    out = []
    for folder in sorted((p for p in root.iterdir() if p.is_dir() and CAPTURE_NAME.match(p.name)), reverse=True):
        pcap = folder / PCAP_FILE
        out.append(
            {
                "name": folder.name,
                "verdict": read_verdict(folder),
                "has_packets": pcap.is_file(),
                "size_bytes": pcap.stat().st_size if pcap.is_file() else 0,
            }
        )
    return out


@router.get("/captures/{name}")
def capture_detail(
    name: str,
    _: AdminDep,
    svc: SvcDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=MAX_PAGE),
) -> dict[str, Any]:
    path = capture_path(svc, name)
    s = summarize(path)
    page: list[dict[str, Any]] = []
    for p in read_packets(path):
        if p.number <= offset:
            continue
        if len(page) >= limit:
            break
        page.append(
            {
                "number": p.number,
                "time": p.time,
                "length": p.length,
                "src": p.src,
                "dst": p.dst,
                "protocol": p.protocol,
                "ports": p.ports,
                "info": p.info,
            }
        )
    return {
        "name": name,
        "verdict": read_verdict(captures_dir(svc) / name),
        "summary": {
            "packets": s.packets,
            "bytes": s.bytes,
            "first": s.first,
            "last": s.last,
            "truncated": s.truncated,
            "protocols": [{"name": k, "count": v} for k, v in Counter(s.protocols).most_common(20)],
            "talkers": [{"address": k, "count": v} for k, v in s.talkers.most_common(10)],
        },
        "offset": offset,
        "limit": limit,
        "packets": page,
    }
