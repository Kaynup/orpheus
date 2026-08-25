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


def test_vector_store_dynamic_hnsw_metadata(temp_vector_store):
    """Verify collection initialization dynamically assigns HNSW space matching embedding manager."""
    expected_space = temp_vector_store.embedding_manager.distance_metric
    actual_space = temp_vector_store._collection.metadata.get("hnsw:space")
    assert actual_space == expected_space


def test_vector_store_reset_collection_preserves_metadata(temp_vector_store):
    """Verify reset_collection recreates collection and preserves dynamic HNSW metadata."""
    chunks = [
        TextChunk(
            chunk_id="reset_doc_0",
            chunk_index=0,
            content="Temporary chunk before collection reset.",
            doc_id="reset_doc",
            source_filename="temp.txt",
            page_number=1,
            start_char=0,
            end_char=40,
            token_count_estimate=10,
        )
    ]
    temp_vector_store.add_chunks(chunks)
    assert temp_vector_store._collection.count() == 1

    temp_vector_store.reset_collection()
    assert temp_vector_store._collection.count() == 0

    expected_space = temp_vector_store.embedding_manager.distance_metric
    assert temp_vector_store._collection.metadata.get("hnsw:space") == expected_space


def test_vector_store_batch_insertion_slicing(monkeypatch, temp_vector_store):
    """Verify batch insertion safely splits chunks into configured batch_size increments."""
    test_batch_size = 2
    monkeypatch.setattr("app.storage.vector_store.config.storage.batch_size", test_batch_size)

    total_chunks_to_create = test_batch_size + 3  # Dynamically exceeds batch limit (e.g. 5 chunks in batches of 2)
    chunks = [
        TextChunk(
            chunk_id=f"batch_doc_chunk_{i}",
            chunk_index=i,
            content=f"Batch test document chunk index number {i} for pagination testing.",
            doc_id="batch_doc",
            source_filename="batch_test.txt",
            page_number=1,
            start_char=i * 50,
            end_char=(i + 1) * 50,
            token_count_estimate=12,
        )
        for i in range(total_chunks_to_create)
    ]

    inserted = temp_vector_store.add_chunks(chunks)
    assert inserted == total_chunks_to_create
    assert temp_vector_store._collection.count() == total_chunks_to_create


def test_vector_store_empty_add_chunks(temp_vector_store):
    """Verify add_chunks returns 0 gracefully when empty list is provided."""
    assert temp_vector_store.add_chunks([]) == 0


def test_vector_store_similarity_delegation(temp_vector_store):
    """Verify similarity values in search results are delegated through embedding_manager.distance_to_similarity."""
    chunks = [
        TextChunk(
            chunk_id="sim_doc_0",
            chunk_index=0,
            content="Monocrystalline solar cells convert photovoltaic energy efficiently.",
            doc_id="sim_doc",
            source_filename="solar_spec.txt",
            page_number=1,
            start_char=0,
            end_char=70,
            token_count_estimate=15,
        )
    ]
    temp_vector_store.add_chunks(chunks)

    results = temp_vector_store.search("photovoltaic solar energy", top_k=1)
    assert len(results) == 1
    res = results[0]

    raw_dist = res["distance"]
    expected_sim = temp_vector_store.embedding_manager.distance_to_similarity(raw_dist)
    assert res["similarity"] == pytest.approx(expected_sim)

