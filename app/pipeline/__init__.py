"""Pipeline package public API exports.

All pipeline types, factory functions, and event primitives are available from this
package root so that consumers only need a single import path::

    from app.pipeline import (
        BaseRAGPipeline,
        create_rag_pipeline,
        DocumentIngestionPipeline,
        QueryInferencePipeline,
        IngestionResult,
        QueryResult,
        RAGPipeline,
        EventStage,
        EventStatus,
        PipelineEvent,
        EventCallback,
    )
"""

from app.pipeline.base import (
    BaseInferencePipeline,
    BaseIngestionPipeline,
    BasePipeline,
    BaseRAGPipeline,
)
from app.pipeline.events import (
    EventCallback,
    EventStage,
    EventStatus,
    PipelineEvent,
)
from app.pipeline.factory import (
    create_inference_pipeline,
    create_ingestion_pipeline,
    create_rag_pipeline,
)
from app.pipeline.inference_pipeline import QueryInferencePipeline
from app.pipeline.ingestion_pipeline import DocumentIngestionPipeline
from app.pipeline.models import IngestionResult, QueryResult
from app.pipeline.rag_pipeline import RAGPipeline

__all__ = [
    # Abstract bases
    "BasePipeline",
    "BaseIngestionPipeline",
    "BaseInferencePipeline",
    "BaseRAGPipeline",
    # Events
    "EventCallback",
    "EventStage",
    "EventStatus",
    "PipelineEvent",
    # Factory functions
    "create_rag_pipeline",
    "create_ingestion_pipeline",
    "create_inference_pipeline",
    # Concrete pipelines
    "DocumentIngestionPipeline",
    "QueryInferencePipeline",
    "RAGPipeline",
    # Result dataclasses
    "IngestionResult",
    "QueryResult",
]
