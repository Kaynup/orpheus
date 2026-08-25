"""Ingestion package exports."""

from app.ingestion.parser import (
    BaseDocumentParser,
    DocumentParsingError,
    PageContent,
    ParsedDocument,
    PARSER_REGISTRY,
    PDFDocumentParser,
    TXTDocumentParser,
    parse_document,
    parse_pdf,
    parse_txt,
)
from app.ingestion.validator import (
    FileValidationError,
    sanitize_filename,
    validate_file,
)

__all__ = [
    # Abstract base & registry
    "BaseDocumentParser",
    "PARSER_REGISTRY",
    "TXTDocumentParser",
    "PDFDocumentParser",
    # Data models
    "DocumentParsingError",
    "PageContent",
    "ParsedDocument",
    # Functions
    "parse_document",
    "parse_pdf",
    "parse_txt",
    # Validator
    "FileValidationError",
    "sanitize_filename",
    "validate_file",
]
