from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from app.backup import MANIFEST, BackupError, create_backup, restore_backup
from db.models import User
from db.session import Database


def _make_data_dir(root: Path) -> Path:
    data = root / "data"
    db = Database(data / "airgap.db")
    with db.session() as s:
        s.add(User(username="admin", password_hash="x", role="admin"))
        s.commit()
    db.engine.dispose()
    (data / "keys").mkdir(parents=True)
    (data / "keys" / "attestation.key").write_bytes(b"key-bytes")
    (data / "documents").mkdir()
    (data / "documents" / "policy.txt").write_text("minimum attendance is 75", encoding="utf-8")
    return data


def _users(db_path: Path) -> list[str]:
    c = sqlite3.connect(db_path)
    try:
        return [r[0] for r in c.execute("select username from users order by username")]
    finally:
        c.close()


def _rewrite(archive: Path, mutate: Callable[[dict[str, bytes]], None]) -> None:
    members: dict[str, bytes] = {}
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            fh = tar.extractfile(m)
            assert fh is not None
            members[m.name] = fh.read()
    mutate(members)
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_round_trip_restores_database_keys_and_documents(tmp_path: Path) -> None:
    src = _make_data_dir(tmp_path / "a")
    archive = tmp_path / "out" / "backup.tar.gz"

    manifest = create_backup(src, archive)
    assert set(manifest["files"]) == {"airgap.db", "keys/attestation.key", "documents/policy.txt"}

    dst = tmp_path / "b" / "data"
    restored = restore_backup(archive, dst)

    assert restored == manifest
    assert _users(dst / "airgap.db") == ["admin"]
    assert (dst / "keys" / "attestation.key").read_bytes() == b"key-bytes"
    assert (dst / "documents" / "policy.txt").read_text(encoding="utf-8") == "minimum attendance is 75"


def test_restore_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    src = _make_data_dir(tmp_path / "a")
    archive = tmp_path / "backup.tar.gz"
    create_backup(src, archive)

    with pytest.raises(BackupError, match="already present"):
        restore_backup(archive, src)


def test_force_moves_existing_data_aside(tmp_path: Path) -> None:
    src = _make_data_dir(tmp_path / "a")
    archive = tmp_path / "backup.tar.gz"
    create_backup(src, archive)
    (src / "documents" / "policy.txt").write_text("changed after backup", encoding="utf-8")

    restore_backup(archive, src, force=True)

    assert (src / "documents" / "policy.txt").read_text(encoding="utf-8") == "minimum attendance is 75"
    moved = list(src.glob("documents.before-restore-*"))
    assert len(moved) == 1
    assert (moved[0] / "policy.txt").read_text(encoding="utf-8") == "changed after backup"


def test_tampered_document_is_rejected_and_nothing_is_written(tmp_path: Path) -> None:
    src = _make_data_dir(tmp_path / "a")
    archive = tmp_path / "backup.tar.gz"
    create_backup(src, archive)
    _rewrite(archive, lambda m: m.__setitem__("documents/policy.txt", b"forged policy"))

    dst = tmp_path / "b" / "data"
    with pytest.raises(BackupError, match=r"hash mismatch for documents/policy\.txt"):
        restore_backup(archive, dst)
    assert not (dst / "airgap.db").exists()
    assert not (dst / "documents").exists()


def test_extra_member_not_in_manifest_is_rejected(tmp_path: Path) -> None:
    src = _make_data_dir(tmp_path / "a")
    archive = tmp_path / "backup.tar.gz"
    create_backup(src, archive)
    _rewrite(archive, lambda m: m.__setitem__("keys/extra.key", b"planted"))

    with pytest.raises(BackupError, match="do not match the manifest"):
        restore_backup(archive, tmp_path / "b" / "data")


def test_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    src = _make_data_dir(tmp_path / "a")
    archive = tmp_path / "backup.tar.gz"
    create_backup(src, archive)

    def add_escape(m: dict[str, bytes]) -> None:
        manifest = json.loads(m[MANIFEST])
        manifest["files"]["../escape.txt"] = "0" * 64
        m[MANIFEST] = json.dumps(manifest).encode("utf-8")
        m["../escape.txt"] = b"outside"

    _rewrite(archive, add_escape)

    dst = tmp_path / "b" / "data"
    with pytest.raises(BackupError, match="unsafe"):
        restore_backup(archive, dst)
    assert not (tmp_path / "b" / "escape.txt").exists()


def test_archive_without_manifest_is_rejected(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.tar.gz"
    with tarfile.open(bogus, "w:gz") as tar:
        info = tarfile.TarInfo("airgap.db")
        info.size = 0
        tar.addfile(info, io.BytesIO(b""))

    with pytest.raises(BackupError, match=r"no MANIFEST\.json"):
        restore_backup(bogus, tmp_path / "b" / "data")


def test_backup_without_database_fails_cleanly(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BackupError, match="no database"):
        create_backup(empty, tmp_path / "out.tar.gz")
