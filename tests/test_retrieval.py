"""Unit tests for semantic retrieval and confidence thresholding."""

import pytest
from app.chunking.text_splitter import TextChunk
from app.retrieval.retriever import SemanticRetriever
from app.storage.vector_store import VectorStore


@pytest.fixture
def populated_retriever(tmp_path):
    store = VectorStore(persist_dir=str(tmp_path / "chroma_retrieval"), collection_name="test_retrieval")
    chunks = [
        TextChunk(
            chunk_id="c1",
            chunk_index=0,
            content="Acme Corporation core working hours are 10:00 AM to 3:00 PM Eastern Time.",
            doc_id="d1",
            source_filename="acme_policy.txt",
            page_number=1,
            start_char=0,
            end_char=80,
            token_count_estimate=20,
        ),
        TextChunk(
            chunk_id="c2",
            chunk_index=1,
            content="Canary deployment routes 5% of traffic initially to monitor error rates.",
            doc_id="d2",
            source_filename="cloud_guide.txt",
            page_number=1,
            start_char=0,
            end_char=75,
            token_count_estimate=18,
        ),
    ]
    store.add_chunks(chunks)
    return SemanticRetriever(vector_store=store)


def test_retrieval_matches_relevant_chunk(populated_retriever):
    output = populated_retriever.retrieve("What are the core work hours?", top_k=2)
    assert output.has_relevant_context is True
    assert len(output.chunks) > 0
    top_chunk = output.chunks[0]
    assert "10:00 AM to 3:00 PM" in top_chunk.content
    assert top_chunk.source_filename == "acme_policy.txt"
    assert top_chunk.is_confident is True


def test_retrieval_empty_query(populated_retriever):
    output = populated_retriever.retrieve("")
    assert output.has_relevant_context is False
    assert len(output.chunks) == 0
