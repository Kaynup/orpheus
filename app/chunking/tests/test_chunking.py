"""Unit tests for recursive boundary-aware text chunking and provenance."""

import pytest
from app.chunking.text_splitter import RecursiveTextSplitter, TextChunk
from app.chunking.tokenizer import estimate_tokens
from app.ingestion.parser import PageContent, ParsedDocument


def test_chunking_provenance():
    sample_text = "Paragraph 1 is here.\n\nParagraph 2 is here with more detailed information.\n\nParagraph 3 contains extra guidelines."
    doc = ParsedDocument(
        doc_id="test-doc-123",
        filename="handbook.txt",
        file_type="txt",
        file_path="/tmp/handbook.txt",
        total_chars=len(sample_text),
        checksum="abcdef123456",
        pages=[
            PageContent(
                page_number=1,
                text=sample_text,
                char_count=len(sample_text),
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
        assert len(chunk.content) > 0
        assert chunk.token_count_estimate == estimate_tokens(chunk.content)


def test_chunking_multipage_provenance():
    """Verify chunking across multi-page documents preserves page numbers and sequential indexing."""
    page_1_text = "Page 1 content discussing Acme hybrid work guidelines and core collaboration hours."
    page_2_text = "Page 2 content detailing equipment reimbursement procedures and submit deadlines."

    doc = ParsedDocument(
        doc_id="multi-page-doc",
        filename="policy_multipage.txt",
        file_type="txt",
        file_path="/tmp/policy_multipage.txt",
        total_chars=len(page_1_text) + len(page_2_text),
        checksum="multi123456",
        pages=[
            PageContent(page_number=1, text=page_1_text, char_count=len(page_1_text)),
            PageContent(page_number=2, text=page_2_text, char_count=len(page_2_text)),
        ],
    )

    splitter = RecursiveTextSplitter(chunk_size=40, chunk_overlap=5)
    chunks = splitter.chunk_document(doc)

    assert len(chunks) >= 2
    page_1_chunks = [c for c in chunks if c.page_number == 1]
    page_2_chunks = [c for c in chunks if c.page_number == 2]

    assert len(page_1_chunks) > 0
    assert len(page_2_chunks) > 0
    assert all(c.source_filename == "policy_multipage.txt" for c in chunks)
    assert all(c.doc_id == "multi-page-doc" for c in chunks)


def test_chunking_overlap_constraint():
    with pytest.raises(ValueError, match="chunk_overlap.*must be strictly less than chunk_size"):
        RecursiveTextSplitter(chunk_size=100, chunk_overlap=100)


def test_tokenizer_estimation():
    """Verify token estimation adheres to mathematical contract len(text)//4 with non-empty minimum of 1."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("word") == 1

    test_sentence = "This is a longer sentence with many words that will evaluate to more tokens."
    assert estimate_tokens(test_sentence) == max(1, len(test_sentence) // 4)

    # Dynamic invariant verification across multiple lengths
    for length in [1, 3, 4, 8, 15, 64, 256]:
        generated_string = "a" * length
        expected_tokens = max(1, length // 4)
        assert estimate_tokens(generated_string) == expected_tokens


def test_configurable_separators():
    doc = ParsedDocument(
        doc_id="test-doc-456",
        filename="custom.txt",
        file_type="txt",
        file_path="/tmp/custom.txt",
        total_chars=7,
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

