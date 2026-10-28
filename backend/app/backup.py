"""Backup and restore of the data directory (database, attestation keys, uploaded documents).

Archive layout (gzip-compressed tar):
    MANIFEST.json   format id, creation time, SHA-256 of every other member
    airgap.db       consistent snapshot taken with the SQLite backup API (WAL-safe)
    keys/...        attestation keys, JWT secret, passphrase file
    documents/...   uploaded source documents

The archive is NOT encrypted. It contains the JWT secret and the attestation key file, so store it
like the rest of the sensitive data. Restore stops the app first; it does not hot-swap a live database.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

FORMAT = "airgap-backup-v1"
MANIFEST = "MANIFEST.json"
DB_NAME = "airgap.db"
TREES = ("keys", "documents")


class BackupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot_db(src: Path, dst: Path) -> None:
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("database snapshot failed integrity_check")
        finally:
            target.close()
    finally:
        source.close()


def create_backup(data_dir: Path, out: Path) -> dict[str, Any]:
    """Write a backup of ``data_dir`` to ``out`` and return the manifest."""
    db_path = data_dir / DB_NAME
    if not db_path.is_file():
        raise BackupError(f"no database at {db_path}")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f".backup-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        snapshot = staging / DB_NAME
        _snapshot_db(db_path, snapshot)
        files: dict[str, str] = {DB_NAME: _sha256(snapshot)}
        for tree in TREES:
            root = data_dir / tree
            if not root.is_dir():
                continue
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                rel = path.relative_to(data_dir).as_posix()
                files[rel] = _sha256(path)
        manifest = {
            "format": FORMAT,
            "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": files,
        }
        tmp_out = out.with_name(out.name + ".partial")
        with tarfile.open(tmp_out, "w:gz") as tar:
            data = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            info = tarfile.TarInfo(MANIFEST)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            tar.add(snapshot, arcname=DB_NAME)
            for rel in files:
                if rel == DB_NAME:
                    continue
                tar.add(data_dir / rel, arcname=rel)
        tmp_out.replace(out)
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and name != "" and name != MANIFEST


def restore_backup(archive: Path, data_dir: Path, force: bool = False) -> dict[str, Any]:
    """Verify ``archive`` and restore it into ``data_dir``.

    Every member is hash-checked against the manifest before anything is written to ``data_dir``.
    Existing database, keys and documents are moved aside (not deleted) when ``force`` is set.
    """
    if not archive.is_file():
        raise BackupError(f"backup not found: {archive}")
    existing = [name for name in (DB_NAME, *TREES) if (data_dir / name).exists()]
    if existing and not force:
        raise BackupError(f"already present in {data_dir}: {', '.join(existing)}; pass force to move them aside")

    data_dir.mkdir(parents=True, exist_ok=True)
    staging = data_dir.parent / f".restore-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = {m.name: m for m in tar.getmembers()}
            if MANIFEST not in members:
                raise BackupError("archive has no MANIFEST.json")
            manifest_fh = tar.extractfile(members[MANIFEST])
            assert manifest_fh is not None
            manifest: dict[str, Any] = json.loads(manifest_fh.read().decode("utf-8"))
            if manifest.get("format") != FORMAT:
                raise BackupError(f"unsupported backup format: {manifest.get('format')!r}")
            files: dict[str, str] = manifest["files"]
            if set(members) - {MANIFEST} != set(files):
                raise BackupError("archive members do not match the manifest")
            for name, member in members.items():
                if name == MANIFEST:
                    continue
                if not _safe_member(name) or not member.isfile():
                    raise BackupError(f"unsafe or non-file member: {name!r}")
                src = tar.extractfile(member)
                assert src is not None
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                h = hashlib.sha256()
                with target.open("wb") as out_fh:
                    while chunk := src.read(1024 * 1024):
                        h.update(chunk)
                        out_fh.write(chunk)
                if h.hexdigest() != files[name]:
                    raise BackupError(f"hash mismatch for {name}: archive is corrupt or was modified")

        restored_db = staging / DB_NAME
        check = sqlite3.connect(restored_db)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("restored database failed integrity_check")
        finally:
            check.close()

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        for name in (DB_NAME, "airgap.db-wal", "airgap.db-shm", *TREES):
            current = data_dir / name
            if force and current.exists():
                current.rename(data_dir / f"{name}.before-restore-{stamp}")
        for name in (DB_NAME, *TREES):
            src_item = staging / name
            if src_item.exists():
                (data_dir / name).parent.mkdir(parents=True, exist_ok=True)
                src_item.replace(data_dir / name)
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)
