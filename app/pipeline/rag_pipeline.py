"""RAG Pipeline Orchestrator — Facade over modular sub-pipelines.

``RAGPipeline`` is the unified entry point that satisfies ``BaseRAGPipeline``.
All business logic lives in the dedicated sub-pipelines:

- Stages 1–3 (Ingestion):  ``DocumentIngestionPipeline``
- Stages 4–7 (Inference):  ``QueryInferencePipeline``

Result dataclasses are re-exported here for backward compatibility so that all
existing import paths continue to work without modification::

    from app.pipeline.rag_pipeline import IngestionResult, QueryResult, RAGPipeline
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.config import AppConfig
from app.logging_config import logger
from app.pipeline.base import BaseInferencePipeline, BaseIngestionPipeline, BaseRAGPipeline
from app.pipeline.events import EventCallback
from app.pipeline.models import IngestionResult, QueryResult  # noqa: F401 – re-exported for backward compat
from app.storage.vector_store import VectorStore

__all__ = [
    "IngestionResult",
    "QueryResult",
    "RAGPipeline",
]


class RAGPipeline(BaseRAGPipeline):
    """Unified RAG pipeline facade combining ingestion and inference sub-pipelines.

    Delegates all stage logic to:
    - ``DocumentIngestionPipeline`` — Stages 1–3
    - ``QueryInferencePipeline``   — Stages 4–7

    The ``VectorStore`` is shared between both sub-pipelines so that documents ingested
    by ``ingest_document`` are immediately available to ``answer_query``.

    Args:
        app_config:         Optional ``AppConfig`` override; falls back to global singleton.
        vector_store:       Optional shared ``VectorStore``; created from config if not provided.
        ingestion_pipeline: Optional ``BaseIngestionPipeline`` override for testing / DI.
        inference_pipeline: Optional ``BaseInferencePipeline`` override for testing / DI.
    """

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        vector_store: Optional[VectorStore] = None,
        ingestion_pipeline: Optional[BaseIngestionPipeline] = None,
        inference_pipeline: Optional[BaseInferencePipeline] = None,
    ) -> None:
        super().__init__(app_config=app_config)

        # Shared VectorStore — single source of truth for both sub-pipelines
        self.vector_store = vector_store or VectorStore(
            persist_dir=self.config.storage.persist_dir,
            collection_name=self.config.storage.collection_name,
        )

        # Lazy imports to avoid circular references at module-load time
        if ingestion_pipeline is None:
            from app.pipeline.ingestion_pipeline import DocumentIngestionPipeline

            ingestion_pipeline = DocumentIngestionPipeline(
                app_config=self.config,
                vector_store=self.vector_store,
            )
        if inference_pipeline is None:
            from app.pipeline.inference_pipeline import QueryInferencePipeline

            inference_pipeline = QueryInferencePipeline(
                app_config=self.config,
                vector_store=self.vector_store,
            )

        self._ingestion: BaseIngestionPipeline = ingestion_pipeline
        self._inference: BaseInferencePipeline = inference_pipeline

        logger.debug(
            "RAGPipeline initialised [collection=%s, ingestion=%s, inference=%s]",
            self.vector_store.collection_name,
            type(self._ingestion).__name__,
            type(self._inference).__name__,
        )


    # BaseIngestionPipeline

    def ingest_document(
        self,
        file_path: str | Path,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> IngestionResult:
        """Delegate to the ``DocumentIngestionPipeline``."""
        return self._ingestion.ingest_document(
            file_path=file_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            event_callback=event_callback,
        )

    def delete_document(self, doc_id: str) -> bool:
        """Delegate to the ``DocumentIngestionPipeline``."""
        return self._ingestion.delete_document(doc_id=doc_id)


    # BaseInferencePipeline

    def answer_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> QueryResult:
        """Delegate to the ``QueryInferencePipeline``."""
        return self._inference.answer_query(
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
            model=model,
            temperature=temperature,
            event_callback=event_callback,
        )
