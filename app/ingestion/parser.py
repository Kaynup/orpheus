"""Document parsing for Plain Text (.txt) and PDF (.pdf) files with full provenance tracking."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import pypdf

from app.ingestion.validator import sanitize_filename, validate_file
from app.logging_config import logger


class DocumentParsingError(Exception):
    """Raised when parsing fails on a malformed or corrupted document."""
    pass


@dataclass
class PageContent:
    """Represents a discrete section or page from a document."""
    page_number: int
    text: str
    char_count: int


@dataclass
class ParsedDocument:
    """Full representation of an ingested document with source provenance."""
    doc_id: str
    filename: str
    file_type: str
    file_path: str
    total_chars: int
    checksum: str
    pages: List[PageContent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """Concatenated text of all pages."""
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file for deduplication and provenance."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_txt(file_path: Path) -> ParsedDocument:
    """Parse a plain text file into a ParsedDocument."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as err:
        logger.error("Failed to read text file %s: %s", file_path, err)
        raise DocumentParsingError(f"Could not read text file '{file_path.name}': {err}") from err

    checksum = compute_sha256(file_path)
    clean_text = text.strip()
    page = PageContent(page_number=1, text=clean_text, char_count=len(clean_text))

    return ParsedDocument(
        doc_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"file://{checksum}")),
        filename=sanitize_filename(file_path.name),
        file_type="txt",
        file_path=str(file_path.resolve()),
        total_chars=len(clean_text),
        checksum=checksum,
        pages=[page],
        metadata={"line_count": len(text.splitlines()), "encoding": "utf-8"},
    )


def parse_pdf(file_path: Path) -> ParsedDocument:
    """Parse a PDF file page-by-page using pypdf into a ParsedDocument."""
    checksum = compute_sha256(file_path)
    pages: List[PageContent] = []
    total_chars = 0

    try:
        reader = pypdf.PdfReader(str(file_path))
        num_pages = len(reader.pages)
        if num_pages == 0:
            raise DocumentParsingError(f"PDF '{file_path.name}' contains 0 pages.")

        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            clean_page_text = page_text.strip()
            total_chars += len(clean_page_text)
            pages.append(
                PageContent(
                    page_number=idx + 1,
                    text=clean_page_text,
                    char_count=len(clean_page_text),
                )
            )
    except Exception as err:
        logger.error("Failed to parse PDF %s: %s", file_path, err)
        raise DocumentParsingError(f"Failed to parse PDF document '{file_path.name}': {err}") from err

    return ParsedDocument(
        doc_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"file://{checksum}")),
        filename=sanitize_filename(file_path.name),
        file_type="pdf",
        file_path=str(file_path.resolve()),
        total_chars=total_chars,
        checksum=checksum,
        pages=pages,
        metadata={"page_count": len(pages)},
    )


def parse_document(file_path: str | Path) -> ParsedDocument:
    """
    Validate and parse a document (.txt or .pdf) into a structured ParsedDocument.
    """
    path = Path(file_path)
    validate_file(path)

    ext = path.suffix.lower()
    logger.info("Parsing document: %s (type: %s, size: %d bytes)", path.name, ext, path.stat().st_size)

    if ext == ".txt":
        doc = parse_txt(path)
    elif ext == ".pdf":
        doc = parse_pdf(path)
    else:
        raise DocumentParsingError(f"Unsupported file extension: {ext}")

    logger.info(
        "Successfully parsed %s: doc_id=%s, pages=%d, total_chars=%d",
        doc.filename,
        doc.doc_id[:8],
        len(doc.pages),
        doc.total_chars,
    )
    return doc
