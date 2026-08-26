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


def test_retrieval_dynamic_score_threshold_override(populated_retriever):
    """Verify retriever dynamically respects score_threshold overrides."""
    query = "What are the core work hours?"

    # Very strict threshold (rejects matches as not confident)
    strict_output = populated_retriever.retrieve(query, score_threshold=0.001)
    assert strict_output.has_relevant_context is False
    assert all(c.is_confident is False for c in strict_output.chunks)

    # Relaxed threshold (accepts matches as confident)
    relaxed_output = populated_retriever.retrieve(query, score_threshold=2.0)
    assert relaxed_output.has_relevant_context is True
    assert all(c.is_confident is True for c in relaxed_output.chunks)


def test_retrieval_dynamic_top_k_slicing(populated_retriever):
    """Verify retriever dynamically respects top_k limits."""
    query = "deployment and working hours"

    out_1 = populated_retriever.retrieve(query, top_k=1)
    assert len(out_1.chunks) == 1

    out_2 = populated_retriever.retrieve(query, top_k=2)
    assert len(out_2.chunks) == 2


def test_retrieval_doc_id_filter(populated_retriever):
    """Verify retriever filters results by specific doc_id."""
    query = "traffic and core working hours"

    out_d1 = populated_retriever.retrieve(query, filter_doc_id="d1")
    assert all(c.doc_id == "d1" for c in out_d1.chunks)

    out_d2 = populated_retriever.retrieve(query, filter_doc_id="d2")
    assert all(c.doc_id == "d2" for c in out_d2.chunks)


def test_retrieval_output_properties(populated_retriever):
    """Verify summary metric properties on RetrievalOutput."""
    out = populated_retriever.retrieve("core working hours", top_k=2)
    assert len(out.chunks) > 0
    assert out.highest_similarity == pytest.approx(max(c.similarity for c in out.chunks))
    assert out.lowest_distance == pytest.approx(min(c.distance for c in out.chunks))
