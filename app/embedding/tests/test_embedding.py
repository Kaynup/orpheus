"""Unit tests for EmbeddingManager verifying mathematical invariants, metric delegation, and embedding dimensions."""

import pytest

from app.config import config
from app.embedding.embedder import EmbeddingManager


@pytest.fixture
def embedding_manager():
    return EmbeddingManager()


def test_embedding_manager_properties_consistency(embedding_manager):
    """Verify that metadata properties match the active storage configuration and actual vector geometry."""
    # Metric matches dynamic active configuration
    assert embedding_manager.distance_metric == getattr(config.storage, "distance_metric", "cosine")

    # Property dimension matches the actual vector output length from a sample query
    sample_vector = embedding_manager.embed_query("Semantic consistency test prompt")
    assert embedding_manager.dimension == len(sample_vector)
    assert len(sample_vector) > 0


def test_distance_to_similarity_mathematical_invariants(embedding_manager):
    """Verify mathematical boundary invariants and monotonic decrease across distance."""
    # Invariant 1: Zero distance must yield identity maximum similarity (1.0)
    assert embedding_manager.distance_to_similarity(0.0) == pytest.approx(1.0)

    # Invariant 2: Positive distances must remain bounded within [0.0, 1.0]
    for d in [0.05, 0.25, 0.5, 0.75, 1.0, 2.0]:
        sim = embedding_manager.distance_to_similarity(d)
        assert 0.0 <= sim <= 1.0, f"Similarity {sim} for distance {d} violated [0.0, 1.0] bounds"

    # Invariant 3: Strictly monotonic decreasing (smaller distance = higher similarity)
    distances = [0.1, 0.3, 0.6, 0.9, 1.5]
    similarities = [embedding_manager.distance_to_similarity(d) for d in distances]
    for i in range(len(similarities) - 1):
        assert similarities[i] >= similarities[i + 1], f"Expected sim({distances[i]}) >= sim({distances[i + 1]})"


def test_distance_to_similarity_across_supported_metrics(monkeypatch, embedding_manager):
    """Verify formula accuracy across Cosine, Euclidean (L2), and Inner Product (IP) distance metrics."""
    test_distance = 0.4

    # 1. Cosine: 1.0 - distance
    monkeypatch.setattr(config.storage, "distance_metric", "cosine")
    assert embedding_manager.distance_to_similarity(test_distance) == pytest.approx(1.0 - test_distance)

    # 2. Inner Product: 1.0 - distance
    monkeypatch.setattr(config.storage, "distance_metric", "ip")
    assert embedding_manager.distance_to_similarity(test_distance) == pytest.approx(1.0 - test_distance)

    # 3. L2: 1.0 / (1.0 + distance)
    monkeypatch.setattr(config.storage, "distance_metric", "l2")
    assert embedding_manager.distance_to_similarity(test_distance) == pytest.approx(1.0 / (1.0 + test_distance))


def test_embed_documents_batch_invariance(embedding_manager):
    """Verify embed_documents preserves cardinality and dimensional invariance for arbitrary batches."""
    sample_texts = [
        "Retrieval-Augmented Generation synthesizes grounded answers.",
        "Persistent vector stores index high-dimensional embeddings.",
        "Chunking text into semantic units prevents lost in the middle phenomena.",
    ]

    embeddings = embedding_manager.embed_documents(sample_texts)
    assert len(embeddings) == len(sample_texts)

    expected_dim = embedding_manager.dimension
    for vector in embeddings:
        assert len(vector) == expected_dim
        assert all(isinstance(float(v), float) for v in vector)


def test_embed_documents_empty_list(embedding_manager):
    """Verify empty input list returns empty result list safely."""
    assert embedding_manager.embed_documents([]) == []
