"""Unit tests for document validation and ingestion parser."""

import uuid
from pathlib import Path

import pytest

from app.config import config
from app.ingestion.parser import (
    PARSER_REGISTRY,
    BaseDocumentParser,
    PageContent,
    ParsedDocument,
    compute_sha256,
    parse_document,
)
from app.ingestion.validator import (
    FileValidationError,
    sanitize_filename,
    validate_file,
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


def test_validate_dynamic_size_limit(tmp_path):
    """Verify validate_file dynamically enforces max_bytes parameter overrides."""
    test_file = tmp_path / "large_doc.txt"
    content = "A" * 200
    test_file.write_text(content)

    # Calling with limit below file size must fail
    limit_below = len(content) - 50
    with pytest.raises(FileValidationError, match="exceeds maximum limit"):
        validate_file(test_file, max_bytes=limit_below)

    # Calling with limit above file size must succeed
    limit_above = len(content) + 50
    is_valid, msg = validate_file(test_file, max_bytes=limit_above)
    assert is_valid is True
    assert "valid" in msg.lower()


def test_validate_dynamic_allowed_extensions(tmp_path):
    """Verify validate_file dynamically enforces allowed_extensions parameter overrides."""
    custom_file = tmp_path / "document.customext"
    custom_file.write_text("Custom content for validation")

    # Rejects when extension is not in custom set
    with pytest.raises(FileValidationError, match="Unsupported file type"):
        validate_file(custom_file, allowed_extensions={".txt", ".pdf"})

    # Accepts when extension is explicitly provided in custom set
    is_valid, msg = validate_file(custom_file, allowed_extensions={".customext"})
    assert is_valid is True


def test_compute_sha256_buffer_invariance(tmp_path):
    """Verify compute_sha256 produces identical hashes across arbitrary read buffer sizes."""
    sample_file = tmp_path / "hash_test.txt"
    sample_file.write_text("Determinism test content for multi-buffer checksum calculation " * 50)

    # Test various buffer sizes against default config buffer size
    hash_default = compute_sha256(sample_file)
    hash_small_buffer = compute_sha256(sample_file, buffer_size=64)
    hash_large_buffer = compute_sha256(sample_file, buffer_size=config.storage.hash_buffer_size * 2)

    assert hash_default == hash_small_buffer
    assert hash_default == hash_large_buffer
    assert len(hash_default) == 64


def test_parse_valid_txt(tmp_path):
    """Verify parse_document extracts text and derives exact SHA-256 and UUID5 identifiers."""
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
    assert doc.pages[0].char_count == len(sample_text)

    # Exact cryptographic derivation verification (no weak 'is not None' checks)
    expected_checksum = compute_sha256(txt_file)
    expected_doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"file://{expected_checksum}"))
    assert doc.checksum == expected_checksum
    assert doc.doc_id == expected_doc_id


def test_parser_registry_dynamic_extensibility(tmp_path):
    """Verify Open-Closed Principle: registering a custom format strategy without editing dispatch code."""
    custom_ext = ".customdoc"

    class CustomDocParser(BaseDocumentParser):
        def parse(self, file_path: Path) -> ParsedDocument:
            text = file_path.read_text(encoding="utf-8")
            checksum = compute_sha256(file_path)
            return ParsedDocument(
                doc_id=f"custom-{checksum[:8]}",
                filename=file_path.name,
                file_type="customdoc",
                file_path=str(file_path.resolve()),
                total_chars=len(text),
                checksum=checksum,
                pages=[PageContent(page_number=1, text=text, char_count=len(text))],
                metadata={"custom_parser": True},
            )

    # Register dynamic strategy
    PARSER_REGISTRY[custom_ext] = CustomDocParser()

    try:
        custom_file = tmp_path / "test_doc.customdoc"
        custom_file.write_text("Hello from custom format parser strategy!")

        doc = parse_document(custom_file)
        assert isinstance(doc, ParsedDocument)
        assert doc.file_type == "customdoc"
        assert doc.metadata.get("custom_parser") is True
        assert doc.pages[0].text == "Hello from custom format parser strategy!"
    finally:
        # Clean up registry
        PARSER_REGISTRY.pop(custom_ext, None)


def test_parse_unsupported_extension_error(tmp_path):
    """Verify parse_document raises FileValidationError for unmapped extensions."""
    unmapped_file = tmp_path / "archive.unmapped"
    unmapped_file.write_text("dummy archive content")

    with pytest.raises(FileValidationError, match="Unsupported file type"):
        parse_document(unmapped_file)
