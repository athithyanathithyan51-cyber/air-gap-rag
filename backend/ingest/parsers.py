"""Document parsers. Each returns a list of Segments (text + page/section location).

All parsing is local. File type is decided by content sniffing (magic bytes),
not by the file extension a user supplied.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass

log = logging.getLogger("airgap.ingest")


class UnsupportedFileError(ValueError):
    pass


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    text: str
    page: int | None  # 1-based page for PDFs, None otherwise
    section: str | None  # nearest heading, if known


MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_MD = "text/markdown"
MIME_TXT = "text/plain"


def sniff_mime(data: bytes, filename: str) -> str:
    """Decide the type from content. The extension only distinguishes markdown from plain text."""
    if data.startswith(b"%PDF-"):
        return MIME_PDF
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return MIME_DOCX
        except zipfile.BadZipFile as exc:
            raise UnsupportedFileError("corrupt zip container") from exc
        raise UnsupportedFileError("zip file is not a .docx document")
    head = data[:8192]
    if b"\x00" in head:
        raise UnsupportedFileError("binary file type is not supported")
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A multi-byte character cut at the 8 KiB boundary is fine; anything else is not text.
        if exc.start < len(head) - 4:
            raise UnsupportedFileError("text file is not valid UTF-8") from exc
    return MIME_MD if filename.lower().endswith((".md", ".markdown")) else MIME_TXT


_WS = re.compile(r"[ \t ]+")  # noqa: RUF001 - intentional NBSP
_MANY_NL = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "\n".join(_WS.sub(" ", line).strip() for line in text.split("\n"))
    return _MANY_NL.sub("\n\n", text).strip()


def _guess_heading(text: str) -> str | None:
    """First short line that looks like a heading (numbered, upper-case, or title-like)."""
    for line in text.split("\n")[:8]:
        s = line.strip()
        if 3 <= len(s) <= 120 and (
            re.match(r"^(\d+(\.\d+)*\.?|[IVX]+\.|chapter|section|unit|experiment|exp\.?)\s", s, re.I)
            or (s.isupper() and len(s.split()) <= 12)
        ):
            return s
    return None


def parse_pdf(data: bytes, max_pages: int) -> tuple[list[Segment], int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("encrypted PDFs are not supported")
        n_pages = len(reader.pages)
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, IndexError, OSError) as exc:
        raise ParseError(f"corrupt PDF: {exc}") from exc
    if n_pages > max_pages:
        raise ParseError(f"PDF has {n_pages} pages; limit is {max_pages}")

    texts: list[str] = []
    for page in reader.pages:
        try:
            texts.append(clean_text(page.extract_text() or ""))
        except Exception as exc:  # noqa: BLE001 - one bad page must not sink the document
            log.warning("pdf_page_extract_failed", extra={"error": str(exc)})
            texts.append("")

    # pdfplumber copes better with some layouts (tables, odd encodings); use it for empty pages.
    empty = [i for i, t in enumerate(texts) if len(t) < 20]
    if empty:
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for i in empty:
                    texts[i] = clean_text(pdf.pages[i].extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            log.warning("pdfplumber_fallback_failed", extra={"error": str(exc)})

    segments: list[Segment] = []
    section: str | None = None
    for i, text in enumerate(texts):
        if not text:
            continue
        section = _guess_heading(text) or section
        segments.append(Segment(text=text, page=i + 1, section=section))
    if not segments:
        raise ParseError("no extractable text (scanned PDF? OCR is not enabled in this release)")
    return segments, n_pages


def parse_docx(data: bytes) -> list[Segment]:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ParseError(f"corrupt DOCX: {exc}") from exc

    segments: list[Segment] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        text = clean_text("\n".join(buf))
        if text:
            segments.append(Segment(text=text, page=None, section=section))
        buf.clear()

    for para in document.paragraphs:
        style = (para.style.name if para.style is not None else "") or ""
        text = para.text.strip()
        if not text:
            continue
        if style.lower().startswith(("heading", "title")):
            flush()
            section = text[:300]
            buf.append(text)
        else:
            buf.append(text)
    flush()
    for table in document.tables:
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        text = clean_text("\n".join(rows))
        if text:
            segments.append(Segment(text=text, page=None, section=section or "Table"))
    if not segments:
        raise ParseError("DOCX contains no text")
    return segments


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_text(data: bytes, markdown: bool) -> list[Segment]:
    text = data.decode("utf-8", errors="replace")
    segments: list[Segment] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = clean_text("\n".join(buf))
        if body:
            segments.append(Segment(text=body, page=None, section=section))
        buf.clear()

    for line in text.splitlines():
        m = _MD_HEADING.match(line) if markdown else None
        if m:
            flush()
            section = m.group(2).strip()[:300]
            buf.append(section)
        else:
            buf.append(line)
    flush()
    if not segments:
        raise ParseError("file is empty")
    return segments


def parse(data: bytes, filename: str, max_pdf_pages: int = 2000) -> tuple[str, list[Segment], int]:
    """Return (mime, segments, page_count)."""
    mime = sniff_mime(data, filename)
    if mime == MIME_PDF:
        segments, pages = parse_pdf(data, max_pdf_pages)
        return mime, segments, pages
    if mime == MIME_DOCX:
        return mime, parse_docx(data), 0
    return mime, parse_text(data, markdown=mime == MIME_MD), 0
