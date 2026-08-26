"""Semantic retrieval module for Orpheus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import RetrievalConfig, config
from app.logging_config import logger
from app.storage.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    """Represents a single retrieved chunk with semantic score and source metadata."""

    rank: int
    chunk_id: str
    content: str
    doc_id: str
    source_filename: str
    page_number: int
    chunk_index: int
    distance: float
    similarity: float
    is_confident: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "chunk_id": self.chunk_id,
            "content": self.content,
            "doc_id": self.doc_id,
            "source_filename": self.source_filename,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "distance": round(self.distance, 4),
            "similarity": round(self.similarity, 4),
            "is_confident": self.is_confident,
            "metadata": self.metadata,
        }


@dataclass
class RetrievalOutput:
    """Comprehensive output of the retrieval stage."""

    query: str
    chunks: List[RetrievedChunk]
    has_relevant_context: bool
    top_k: int
    score_threshold: float
    total_indexed_chunks: int

    @property
    def highest_similarity(self) -> float:
        if not self.chunks:
            return 0.0
        return max(c.similarity for c in self.chunks)

    @property
    def lowest_distance(self) -> float:
        if not self.chunks:
            return 2.0
        return min(c.distance for c in self.chunks)


class SemanticRetriever:
    """
    Executes semantic similarity retrieval against the persistent vector store.
    Filters and scores retrieved chunks based on configurable relevance thresholds.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        retrieval_config: Optional[RetrievalConfig] = None,
    ):
        self.vector_store = vector_store
        self.config = retrieval_config or config.retrieval

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filter_doc_id: Optional[str] = None,
    ) -> RetrievalOutput:
        """
        Execute semantic retrieval for the query string.
        """
        k = top_k or self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold

        clean_query = query.strip()
        if not clean_query:
            logger.warning("Retriever called with empty query.")
            return RetrievalOutput(
                query="",
                chunks=[],
                has_relevant_context=False,
                top_k=k,
                score_threshold=threshold,
                total_indexed_chunks=0,
            )

        where_filter = {"doc_id": filter_doc_id} if filter_doc_id else None

        raw_results = self.vector_store.search(
            query_text=clean_query,
            top_k=k,
            where_filter=where_filter,
        )

        total_chunks = self.vector_store.get_collection_stats()["total_chunks"]

        retrieved_chunks: List[RetrievedChunk] = []
        confident_count = 0

        for r in raw_results:
            dist = r["distance"]
            sim = r["similarity"]
            # Distance <= threshold indicates acceptable semantic proximity
            # The threshold metric (cosine, l2, ip) is determined dynamically via EmbeddingManager
            is_conf = dist <= threshold

            if is_conf:
                confident_count += 1

            chunk_obj = RetrievedChunk(
                rank=r["rank"],
                chunk_id=r["chunk_id"],
                content=r["content"],
                doc_id=r["doc_id"],
                source_filename=r["source_filename"],
                page_number=r["page_number"],
                chunk_index=r["chunk_index"],
                distance=dist,
                similarity=sim,
                is_confident=is_conf,
                metadata=r["metadata"],
            )
            retrieved_chunks.append(chunk_obj)

        has_relevant = len(retrieved_chunks) > 0 and confident_count > 0

        if not has_relevant:
            logger.warning(
                "Retrieval for query '%.50s' yielded no confident matches (retrieved %d chunks, all distance > %.2f)",
                clean_query,
                len(retrieved_chunks),
                threshold,
            )
        else:
            logger.info(
                "Retrieval for '%.50s' succeeded with %d chunks (%d confident, top similarity: %.3f)",
                clean_query,
                len(retrieved_chunks),
                confident_count,
                retrieved_chunks[0].similarity if retrieved_chunks else 0.0,
            )

        return RetrievalOutput(
            query=clean_query,
            chunks=retrieved_chunks,
            has_relevant_context=has_relevant,
            top_k=k,
            score_threshold=threshold,
            total_indexed_chunks=total_chunks,
        )
