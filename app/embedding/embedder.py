"""Embedding management for transforming text into dense vector representations."""

from __future__ import annotations

try:
    __import__("pysqlite3")
    import sys

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

from typing import List

import chromadb.utils.embedding_functions as ef

from app.config import config
from app.logging_config import logger


class EmbeddingManager:
    """
    Manages vector embeddings for text chunks and queries.
    Uses Chroma's DefaultEmbeddingFunction (ONNX-backed all-MiniLM-L6-v2) by default,
    which produces 384-dimensional dense semantic vectors locally without external network latency.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        logger.info("Initializing EmbeddingManager with model: %s", model_name)

        if self.model_name == "all-MiniLM-L6-v2":
            self._ef = ef.DefaultEmbeddingFunction()
        else:
            # Fallback for future models or external providers
            logger.warning("Model %s not explicitly mapped, falling back to DefaultEmbeddingFunction", model_name)
            self._ef = ef.DefaultEmbeddingFunction()

    @property
    def dimension(self) -> int:
        """Return the vector dimension of the current embedding model."""
        if self.model_name == "all-MiniLM-L6-v2":
            return 384
        return 384  # Default fallback

    @property
    def distance_metric(self) -> str:
        """Return the configured distance space metric for vector comparisons."""
        # Read from config if available (will be added in storage-config branch), else cosine
        return getattr(config.storage, "distance_metric", "cosine")

    def distance_to_similarity(self, distance: float) -> float:
        """Convert a raw distance from ChromaDB into a [0.0, 1.0] similarity score."""
        metric = self.distance_metric
        if metric == "cosine":
            return max(0.0, 1.0 - distance)
        elif metric == "ip":
            return max(0.0, 1.0 - distance)
        elif metric == "l2":
            return 1.0 / (1.0 + distance)

        # Default fallback
        return max(0.0, 1.0 - distance)

    def get_embedding_function(self):
        """Return the underlying Chroma-compatible embedding function."""
        return self._ef

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Compute embeddings for a list of document chunk texts."""
        if not texts:
            return []
        logger.debug("Generating embeddings for %d text items...", len(texts))
        embeddings = self._ef(texts)
        logger.debug(
            "Generated %d embeddings (vector dimension: %d)",
            len(embeddings),
            len(embeddings[0]) if embeddings else 0,
        )
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        """Compute embedding for a single user query string."""
        logger.debug("Generating embedding for query: '%.60s...'", query)
        embeddings = self._ef([query])
        return embeddings[0]
