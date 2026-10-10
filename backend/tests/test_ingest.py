from __future__ import annotations

import io
from pathlib import Path

import docx
import pytest
from sqlalchemy import select

from db.models import AuditEvent, Chunk, Document
from ingest.chunker import chunk_segments, estimate_tokens
from ingest.parsers import (
    MIME_DOCX,
    MIME_MD,
    MIME_PDF,
    MIME_TXT,
    ParseError,
    Segment,
    UnsupportedFileError,
    parse,
    sniff_mime,
)
from ingest.pipeline import Ingestor, UploadRejectedError
from tests.conftest import Env
from tests.fakes import make_pdf


def make_docx(paragraphs: list[tuple[str, str]]) -> bytes:
    d = docx.Document()
    for style, text in paragraphs:
        if style == "h1":
            d.add_heading(text, level=1)
        else:
            d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- sniffing


def test_sniff_by_content_not_extension() -> None:
    assert sniff_mime(make_pdf(["hello"]), "notes.txt") == MIME_PDF
    assert sniff_mime(make_docx([("p", "x")]), "x.pdf") == MIME_DOCX
    assert sniff_mime(b"# Title\nbody", "a.md") == MIME_MD
    assert sniff_mime(b"plain text", "a.txt") == MIME_TXT


def test_rejects_binary_and_non_docx_zip() -> None:
    with pytest.raises(UnsupportedFileError):
        sniff_mime(b"MZ\x90\x00\x03\x00\x00\x00", "setup.pdf")
    buf = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("payload.txt", "x")
    with pytest.raises(UnsupportedFileError):
        sniff_mime(buf.getvalue(), "evil.docx")


# ---------------------------------------------------------------- parsers


def test_pdf_pages_and_sections() -> None:
    data = make_pdf(["EXPERIMENT 1\nOhm's law verification using a resistor.", "Page two text about voltmeters."])
    mime, segs, pages = parse(data, "lab.pdf")
    assert mime == MIME_PDF and pages == 2
    assert [s.page for s in segs] == [1, 2]
    assert "Ohm" in segs[0].text
    assert segs[0].section == "EXPERIMENT 1"
    assert segs[1].section == "EXPERIMENT 1"  # carried forward


def test_corrupt_pdf_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse(b"%PDF-1.4\n garbage without objects", "bad.pdf")


def test_docx_headings_become_sections() -> None:
    data = make_docx(
        [
            ("h1", "Attendance Policy"),
            ("p", "Students need 75% attendance."),
            ("h1", "Exams"),
            ("p", "Two internal tests."),
        ]
    )
    mime, segs, _ = parse(data, "policy.docx")
    assert mime == MIME_DOCX
    assert [s.section for s in segs] == ["Attendance Policy", "Exams"]
    assert "75%" in segs[0].text


def test_markdown_sections() -> None:
    _, segs, _ = parse(b"# Intro\nhello\n## Setup\nInstall it.", "x.md")
    assert [s.section for s in segs] == ["Intro", "Setup"]


# ---------------------------------------------------------------- chunker


def test_chunks_respect_budget_overlap_and_boundaries() -> None:
    para = " ".join(f"word{i}" for i in range(120)) + "."
    text = "\n\n".join([para] * 30)
    chunks = chunk_segments([Segment(text, 3, "Sec"), Segment("Short other page.", 4, "Sec")], 200, 30)
    assert len(chunks) > 3
    assert all(estimate_tokens(c.text) <= 200 for c in chunks)
    assert chunks[-1].page == 4 and chunks[-1].text == "Short other page."
    # overlap: the end of chunk 0 reappears at the start of chunk 1
    assert chunks[0].text[-40:].split()[-1] in chunks[1].text[:200]
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_identical_boilerplate_deduplicated() -> None:
    segs = [Segment("Bannari Amman Institute of Technology", p, None) for p in range(1, 6)]
    assert len(chunk_segments(segs)) == 1


def test_overlap_must_be_smaller_than_chunk() -> None:
    with pytest.raises(ValueError):
        chunk_segments([Segment("x", None, None)], 100, 100)


# ---------------------------------------------------------------- pipeline


def ingestor(env: Env, tmp_path: Path, s: object) -> Ingestor:
    return Ingestor(s, env.services.store, env.embedder, tmp_path / "docs", 200, 30)  # type: ignore[arg-type]


async def test_ingest_then_duplicate_then_replace(env: Env, tmp_path: Path) -> None:
    with env.services.db.session() as s:
        ing = ingestor(env, tmp_path, s)
        r1 = await ing.ingest(b"# Fees\nThe hostel fee is 50000 rupees per year.", "fees.md", "admin")
        assert r1.outcome == "ingested" and r1.document.status == "ready" and r1.document.chunk_count == 1
        assert env.services.store.count() == 1
        assert (tmp_path / "docs" / r1.document.sha256).is_file()

        r2 = await ing.ingest(b"# Fees\nThe hostel fee is 50000 rupees per year.", "copy.md", "admin")
        assert r2.outcome == "duplicate" and r2.document.id == r1.document.id
        assert env.embedder.calls == 1  # not re-embedded

        r3 = await ing.ingest(b"# Fees\nThe hostel fee is 60000 rupees per year.", "fees.md", "admin")
        assert r3.outcome == "replaced"
        docs = s.scalars(select(Document)).all()
        assert [d.sha256 for d in docs] == [r3.document.sha256]
        assert env.services.store.count() == 1
        assert s.scalars(select(Chunk)).all()[0].text.endswith("60000 rupees per year.")
        actions = [e.action for e in s.scalars(select(AuditEvent)).all()]
        assert "document.ingested" in actions and "document.replaced" in actions


async def test_corrupt_pdf_rejected_cleanly(env: Env, tmp_path: Path) -> None:
    with env.services.db.session() as s:
        with pytest.raises(UploadRejectedError, match="corrupt PDF"):
            await ingestor(env, tmp_path, s).ingest(b"%PDF-1.7 broken", "broken.pdf", "admin")
        assert s.scalars(select(Document)).all() == []
        assert s.scalars(select(AuditEvent)).all()[-1].action == "document.rejected"


async def test_upload_limits(env: Env, tmp_path: Path) -> None:
    with env.services.db.session() as s:
        ing = Ingestor(s, env.services.store, env.embedder, tmp_path, max_bytes=10)
        with pytest.raises(UploadRejectedError):
            await ing.ingest(b"", "a.txt", "admin")
        with pytest.raises(UploadRejectedError):
            await ing.ingest(b"x" * 11, "a.txt", "admin")
        with pytest.raises(UploadRejectedError):
            await ing.ingest(b"\x7fELF\x00\x00", "a.txt", "admin")
