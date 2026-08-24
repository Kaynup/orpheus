"""Embedding management for transforming text into dense vector representations."""

from __future__ import annotations

try:
    __import__("pysqlite3")
    import sys
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import chromadb.utils.embedding_functions as ef

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
        # Chroma's DefaultEmbeddingFunction downloads ONNX model to cache if not present
        self._ef = ef.DefaultEmbeddingFunction()

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
