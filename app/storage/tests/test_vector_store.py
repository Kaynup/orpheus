"""Unit tests for persistent ChromaDB storage and deduplication."""

import tempfile
import pytest

from app.chunking.text_splitter import TextChunk
from app.storage.vector_store import VectorStore


@pytest.fixture
def temp_vector_store(tmp_path):
    persist_dir = str(tmp_path / "chroma_test_db")
    store = VectorStore(persist_dir=persist_dir, collection_name="test_collection")
    return store


def test_vector_store_add_and_search(temp_vector_store):
    chunks = [
        TextChunk(
            chunk_id="doc1_chunk_0",
            chunk_index=0,
            content="Employees receive 20 days of paid time off per calendar year.",
            doc_id="doc1",
            source_filename="hr_policy.txt",
            page_number=1,
            start_char=0,
            end_char=60,
            token_count_estimate=15,
        ),
        TextChunk(
            chunk_id="doc1_chunk_1",
            chunk_index=1,
            content="Redis caching reduces relational database load by storing keys with a 15-minute TTL.",
            doc_id="doc1",
            source_filename="hr_policy.txt",
            page_number=1,
            start_char=61,
            end_char=140,
            token_count_estimate=20,
        ),
    ]

    inserted = temp_vector_store.add_chunks(chunks)
    assert inserted == 2

    # Query matching PTO
    results = temp_vector_store.search("How many PTO vacation days do employees get?", top_k=2)
    assert len(results) > 0
    top_match = results[0]
    assert "paid time off" in top_match["content"] or "PTO" in top_match["content"]
    assert top_match["source_filename"] == "hr_policy.txt"
    assert top_match["similarity"] > 0.0


def test_vector_store_list_and_delete(temp_vector_store):
    chunks = [
        TextChunk(
            chunk_id="doc2_chunk_0",
            chunk_index=0,
            content="Solar panels have 20% efficiency.",
            doc_id="doc2",
            source_filename="solar.txt",
            page_number=1,
            start_char=0,
            end_char=35,
            token_count_estimate=8,
        )
    ]
    temp_vector_store.add_chunks(chunks)

    docs = temp_vector_store.list_documents()
    assert len(docs) == 1
    assert docs[0]["filename"] == "solar.txt"

    deleted = temp_vector_store.delete_document("doc2")
    assert deleted == 1
    assert len(temp_vector_store.list_documents()) == 0
