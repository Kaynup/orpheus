"""Abstract base pipeline interfaces and protocol contracts for Orpheus.

This module defines the canonical inheritance hierarchy that all Orpheus pipeline
implementations must satisfy. Downstream consumers (Flask routes, CLI, Evaluator, tests)
depend strictly on these abstractions — never on concrete pipeline classes.

Hierarchy:
    BasePipeline
    ├── BaseIngestionPipeline  (Document parsing, chunking, embedding, storage)
    ├── BaseInferencePipeline  (Semantic retrieval, prompt augmentation, generation)
    └── BaseRAGPipeline        (Combined — composite marker interface)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.config import AppConfig
from app.config import config as _global_config
from app.logging_config import logger
from app.pipeline.events import EventCallback, EventStage, EventStatus, PipelineEvent


class BasePipeline(ABC):
    """Root abstract base for all Orpheus pipeline orchestrators.

    Provides:
    - ``config``: resolved ``AppConfig`` instance (injected or global singleton).
    - ``_emit_event()``: shared atomic event dispatch utility for all sub-pipelines.
    """

    def __init__(self, app_config: Optional[AppConfig] = None) -> None:
        self.config: AppConfig = app_config or _global_config

    def _emit_event(
        self,
        events_list: List[PipelineEvent],
        callback: Optional[EventCallback],
        stage: EventStage,
        status: EventStatus,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> PipelineEvent:
        """Create, append, and dispatch an atomic pipeline state transition event."""
        event = PipelineEvent(
            stage=stage,
            status=status,
            message=message,
            data=data or {},
        )
        events_list.append(event)
        if callback:
            try:
                callback(event)
            except Exception as err:
                logger.error("Event callback failed: %s", err)
        return event


class BaseIngestionPipeline(BasePipeline):
    """Abstract interface for the Document Ingestion sub-pipeline.

    Covers Stages 1–3:
        DOC_RECEIVED → TEXT_EXTRACTED → CHUNKS_CREATED →
        EMBEDDINGS_GENERATED → VECTORS_STORED → INDEXING_COMPLETE
    """

    @abstractmethod
    def ingest_document(
        self,
        file_path: str | Path,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> Any:
        """Validate, parse, chunk, embed, and index a document into the vector store.

        Returns:
            IngestionResult with full provenance and stage event log.
        """
        ...

    @abstractmethod
    def delete_document(self, doc_id: str) -> bool:
        """Remove all chunks belonging to ``doc_id`` from the vector store.

        Returns:
            True if deletion succeeded, False if doc_id was not found.
        """
        ...


class BaseInferencePipeline(BasePipeline):
    """Abstract interface for the Query Inference sub-pipeline.

    Covers Stages 4–7:
        QUERY_RECEIVED → QUERY_EMBEDDED → RETRIEVING_CHUNKS →
        CONTEXT_SELECTED → PROMPT_PREPARED → GENERATING_ANSWER → ANSWER_COMPLETE
    """

    @abstractmethod
    def answer_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> Any:
        """Run the full semantic retrieval and grounded generation pipeline.

        Returns:
            QueryResult with answer, citations, retrieved chunks, and stage event log.
        """
        ...

    def stream_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Iterator[PipelineEvent]:
        """Stream pipeline events for a query (optional; default is a no-op iterator).

        Concrete sub-classes may override this for real-time SSE synchronization.
        """
        return iter([])


class BaseRAGPipeline(BaseIngestionPipeline, BaseInferencePipeline):
    """Combined marker interface for end-to-end RAG pipelines.

    Satisfies both ``BaseIngestionPipeline`` and ``BaseInferencePipeline``.
    Use this type when a consumer requires both ingestion and inference capabilities.
    """

    pass
