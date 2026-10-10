"""SQLite engine (WAL mode) and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base


def make_engine(db_path: Path | str) -> Engine:
    url = "sqlite://" if str(db_path) == ":memory:" else f"sqlite:///{Path(db_path).as_posix()}"
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if str(db_path) == ":memory:":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _rec: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()

    Base.metadata.create_all(engine)
    return engine


class Database:
    def __init__(self, db_path: Path | str) -> None:
        self.engine = make_engine(db_path)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.factory()

    def sessions(self) -> Iterator[Session]:
        with self.factory() as s:
            yield s
