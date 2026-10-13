"""Admin command line.

python -m app.cli create-user NAME [--role admin|user]   (password read from prompt or stdin)
python -m app.cli export-chain OUT.jsonl                 (plus OUT.pub with the public key)
python -m app.cli reindex                                (re-chunk all documents with the current chunk settings)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from app.config import Settings, get_settings
from app.services import build_services
from attestation.keys import PUBLIC_FILE
from auth.security import hash_password
from db.audit import audit
from db.models import AttestationBlock, Document, User
from db.session import Database
from ingest.pipeline import Ingestor


def _read_password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    pw = getpass.getpass("Password (min 10 chars): ")
    if pw != getpass.getpass("Repeat password: "):
        raise SystemExit("passwords do not match")
    return pw


async def _reindex(settings: Settings) -> int:
    svc = build_services(settings)
    with svc.db.session() as s:
        ing = Ingestor(
            s, svc.store, svc.embedder, settings.docs_dir, settings.chunk_tokens, settings.chunk_overlap_tokens,
            settings.max_upload_mb * 1024 * 1024, settings.max_pdf_pages,
        )
        docs = s.scalars(select(Document).where(Document.status == "ready").order_by(Document.filename)).all()
        for d in docs:
            old = d.chunk_count
            new = await ing.reindex(d, "cli")
            print(f"{d.filename}: {old} -> {new} chunks")
    print(f"reindexed {len(docs)} documents (chunk_tokens={settings.chunk_tokens})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cu = sub.add_parser("create-user")
    cu.add_argument("username")
    cu.add_argument("--role", choices=["admin", "user"], default="user")
    ex = sub.add_parser("export-chain")
    ex.add_argument("out", type=Path)
    sub.add_parser("reindex")
    args = ap.parse_args(argv)

    settings = get_settings()
    if args.cmd == "reindex":
        return asyncio.run(_reindex(settings))
    db = Database(settings.db_path)
    with db.session() as s:
        if args.cmd == "create-user":
            name = args.username.lower()
            if s.scalar(select(User).where(User.username == name)):
                print(f"user {name} already exists", file=sys.stderr)
                return 1
            try:
                pw_hash = hash_password(_read_password())
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            s.add(User(username=name, password_hash=pw_hash, role=args.role))
            s.commit()
            audit(s, "cli", "user.create", username=name, role=args.role)
            print(f"created {args.role} {name}")
            return 0
        blocks = s.scalars(select(AttestationBlock).order_by(AttestationBlock.index)).all()
        args.out.write_text("".join(b.body + "\n" for b in blocks), encoding="utf-8")
        pub = settings.keys_dir / PUBLIC_FILE
        args.out.with_suffix(".pub").write_bytes(pub.read_bytes())
        print(f"exported {len(blocks)} blocks to {args.out} (public key: {args.out.with_suffix('.pub')})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
