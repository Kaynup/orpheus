"""Unit tests for document validation and ingestion parser."""

import tempfile
from pathlib import Path
import pytest

from app.ingestion.validator import (
    FileValidationError,
    sanitize_filename,
    validate_file,
)
from app.ingestion.parser import (
    DocumentParsingError,
    ParsedDocument,
    parse_document,
)


def test_sanitize_filename():
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("my_document (1).txt") == "my_document (1).txt"
    assert sanitize_filename("..\\..\\malicious.pdf") == "malicious.pdf"


def test_validate_nonexistent_file():
    with pytest.raises(FileValidationError, match="File does not exist"):
        validate_file("/nonexistent/path/doc.txt")


def test_validate_empty_file(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("")
    with pytest.raises(FileValidationError, match="File is empty"):
        validate_file(empty_file)


def test_validate_invalid_extension(tmp_path):
    bad_file = tmp_path / "script.py"
    bad_file.write_text("print('hello')")
    with pytest.raises(FileValidationError, match="Unsupported file type"):
        validate_file(bad_file)


def test_parse_valid_txt(tmp_path):
    txt_file = tmp_path / "sample_policy.txt"
    sample_text = "Acme Corporation remote policy allows working from home 3 days a week."
    txt_file.write_text(sample_text, encoding="utf-8")

    doc = parse_document(txt_file)
    assert isinstance(doc, ParsedDocument)
    assert doc.filename == "sample_policy.txt"
    assert doc.file_type == "txt"
    assert doc.total_chars == len(sample_text)
    assert len(doc.pages) == 1
    assert doc.pages[0].page_number == 1
    assert doc.checksum is not None
    assert doc.doc_id is not None
