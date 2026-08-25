"""Unit tests for recursive boundary-aware text chunking and provenance."""

import pytest
from app.chunking.text_splitter import RecursiveTextSplitter, TextChunk
from app.ingestion.parser import PageContent, ParsedDocument


def test_chunking_provenance():
    doc = ParsedDocument(
        doc_id="test-doc-123",
        filename="handbook.txt",
        file_type="txt",
        file_path="/tmp/handbook.txt",
        total_chars=1200,
        checksum="abcdef123456",
        pages=[
            PageContent(
                page_number=1,
                text="Paragraph 1 is here.\n\nParagraph 2 is here with more detailed information.\n\nParagraph 3 contains extra guidelines.",
                char_count=100,
            )
        ],
    )

    splitter = RecursiveTextSplitter(chunk_size=50, chunk_overlap=10)
    chunks = splitter.chunk_document(doc)

    assert len(chunks) > 0
    for idx, chunk in enumerate(chunks):
        assert isinstance(chunk, TextChunk)
        assert chunk.doc_id == "test-doc-123"
        assert chunk.source_filename == "handbook.txt"
        assert chunk.page_number == 1
        assert chunk.chunk_index == idx
        assert chunk.chunk_id == f"test-doc-123_chunk_{idx}"
        assert chunk.start_char >= 0
        assert chunk.end_char > chunk.start_char
        assert chunk.token_count_estimate > 0


def test_chunking_overlap_constraint():
    with pytest.raises(ValueError, match="chunk_overlap.*must be strictly less than chunk_size"):
        RecursiveTextSplitter(chunk_size=100, chunk_overlap=100)


def test_tokenizer_estimation():
    from app.chunking.tokenizer import estimate_tokens
    
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("word") == 1
    assert estimate_tokens("This is a longer sentence with many words that will evaluate to more tokens.") > 10


def test_configurable_separators():
    doc = ParsedDocument(
        doc_id="test-doc-456",
        filename="custom.txt",
        file_type="txt",
        file_path="/tmp/custom.txt",
        total_chars=100,
        checksum="abcdef123456",
        pages=[
            PageContent(
                page_number=1,
                text="A||B||C",
                char_count=7,
            )
        ],
    )

    # Use a custom separator
    splitter = RecursiveTextSplitter(chunk_size=2, chunk_overlap=0, separators=["||"])
    chunks = splitter.chunk_document(doc)

    assert len(chunks) == 3
    assert chunks[0].content == "A"
    assert chunks[1].content == "B"
    assert chunks[2].content == "C"
