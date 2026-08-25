"""Document parsing for Plain Text (.txt) and PDF (.pdf) files with full provenance tracking.

Architecture:
  Parsers follow the Strategy pattern via BaseDocumentParser. Register new parsers by
  adding an entry to PARSER_REGISTRY — no modifications to parse_document() required.
"""

from __future__ import annotations

import hashlib
import uuid
from abc import ABC, abstractmethod
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


def compute_sha256(path: Path, buffer_size: int = 0) -> str:
    """
    Compute SHA-256 hash of a file for deduplication and provenance.

    Args:
        path: File to hash.
        buffer_size: Read chunk size in bytes. Defaults to config.storage.hash_buffer_size.
    """
    from app.config import config

    effective_buffer = buffer_size if buffer_size > 0 else config.storage.hash_buffer_size

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(effective_buffer):
            hasher.update(chunk)
    return hasher.hexdigest()



# Parser Strategy Abstraction

class BaseDocumentParser(ABC):
    """Abstract base class for all document format parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse the given file into a ParsedDocument."""
        ...


class TXTDocumentParser(BaseDocumentParser):
    """Parser for plain text (.txt) documents."""

    def parse(self, file_path: Path) -> ParsedDocument:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as err:
            logger.error("Failed to read text file %s: %s", file_path, err)
            raise DocumentParsingError(
                f"Could not read text file '{file_path.name}': {err}"
            ) from err

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


class PDFDocumentParser(BaseDocumentParser):
    """Parser for PDF (.pdf) documents using pypdf."""

    def parse(self, file_path: Path) -> ParsedDocument:
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
            raise DocumentParsingError(
                f"Failed to parse PDF document '{file_path.name}': {err}"
            ) from err

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



# Parser Registry — extend here to support new formats without editing below

PARSER_REGISTRY: Dict[str, BaseDocumentParser] = {
    ".txt": TXTDocumentParser(),
    ".pdf": PDFDocumentParser(),
}


# Backward-compatible module-level functions (thin wrappers)

def parse_txt(file_path: Path) -> ParsedDocument:
    """Parse a plain text file into a ParsedDocument. (Backward-compatible wrapper.)"""
    return TXTDocumentParser().parse(file_path)


def parse_pdf(file_path: Path) -> ParsedDocument:
    """Parse a PDF file into a ParsedDocument. (Backward-compatible wrapper.)"""
    return PDFDocumentParser().parse(file_path)


def parse_document(file_path: str | Path) -> ParsedDocument:
    """
    Validate and parse a document into a structured ParsedDocument.

    Dispatches to the appropriate parser via PARSER_REGISTRY based on file extension.
    To support a new format, register a BaseDocumentParser subclass in PARSER_REGISTRY.
    """
    path = Path(file_path)
    validate_file(path)

    ext = path.suffix.lower()
    logger.info(
        "Parsing document: %s (type: %s, size: %d bytes)",
        path.name, ext, path.stat().st_size,
    )

    parser = PARSER_REGISTRY.get(ext)
    if parser is None:
        raise DocumentParsingError(
            f"No registered parser for extension '{ext}'. "
            f"Registered formats: {', '.join(sorted(PARSER_REGISTRY.keys()))}"
        )

    doc = parser.parse(path)

    logger.info(
        "Successfully parsed %s: doc_id=%s, pages=%d, total_chars=%d",
        doc.filename,
        doc.doc_id[:8],
        len(doc.pages),
        doc.total_chars,
    )
    return doc
