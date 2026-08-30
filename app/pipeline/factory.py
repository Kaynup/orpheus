"""Pipeline factory functions for dependency-injected construction of Orpheus pipelines.

All pipeline consumers (Flask routes, CLI, tests) should use these factory functions
instead of directly instantiating concrete pipeline classes. This keeps the instantiation
logic in a single place and makes it trivial to swap implementations or inject overrides.

Usage examples::

    # Full unified pipeline (ingestion + inference)
    from app.pipeline.factory import create_rag_pipeline
    pipeline = create_rag_pipeline()

    # Ingestion-only worker (no LLM components loaded)
    from app.pipeline.factory import create_ingestion_pipeline
    ingest = create_ingestion_pipeline()

    # Inference-only worker (requires a pre-populated VectorStore)
    from app.pipeline.factory import create_inference_pipeline
    inference = create_inference_pipeline(vector_store=shared_store)
"""

from __future__ import annotations

from typing import Optional

from app.config import AppConfig
from app.pipeline.base import BaseInferencePipeline, BaseIngestionPipeline, BaseRAGPipeline
from app.storage.vector_store import VectorStore


def create_rag_pipeline(
    app_config: Optional[AppConfig] = None,
    vector_store: Optional[VectorStore] = None,
) -> BaseRAGPipeline:
    """Create a fully-wired unified ``RAGPipeline`` (ingestion + inference).

    The returned object satisfies ``BaseRAGPipeline``, ``BaseIngestionPipeline``,
    and ``BaseInferencePipeline`` simultaneously.

    Args:
        app_config:   Optional config override; falls back to global singleton.
        vector_store: Optional shared ``VectorStore``; a new one is created if not provided.

    Returns:
        A ``RAGPipeline`` instance cast as ``BaseRAGPipeline``.
    """
    from app.pipeline.rag_pipeline import RAGPipeline

    return RAGPipeline(app_config=app_config, vector_store=vector_store)


def create_ingestion_pipeline(
    app_config: Optional[AppConfig] = None,
    vector_store: Optional[VectorStore] = None,
) -> BaseIngestionPipeline:
    """Create an ingestion-only ``DocumentIngestionPipeline``.

    No LLM generator or retrieval components are loaded, making this the lightest
    pipeline variant suitable for batch indexing and upload workers.

    Args:
        app_config:   Optional config override; falls back to global singleton.
        vector_store: Optional shared ``VectorStore``; a new one is created if not provided.

    Returns:
        A ``DocumentIngestionPipeline`` instance cast as ``BaseIngestionPipeline``.
    """
    from app.pipeline.ingestion_pipeline import DocumentIngestionPipeline

    return DocumentIngestionPipeline(app_config=app_config, vector_store=vector_store)


def create_inference_pipeline(
    app_config: Optional[AppConfig] = None,
    vector_store: Optional[VectorStore] = None,
) -> BaseInferencePipeline:
    """Create an inference-only ``QueryInferencePipeline``.

    Requires a ``VectorStore`` that has already been populated by an ingestion run.
    No parser or chunker components are loaded.

    Args:
        app_config:   Optional config override; falls back to global singleton.
        vector_store: Optional shared ``VectorStore``; a new one is created if not provided.

    Returns:
        A ``QueryInferencePipeline`` instance cast as ``BaseInferencePipeline``.
    """
    from app.pipeline.inference_pipeline import QueryInferencePipeline

    return QueryInferencePipeline(app_config=app_config, vector_store=vector_store)
