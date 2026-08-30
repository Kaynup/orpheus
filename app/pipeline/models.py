"""Pipeline result dataclasses shared across Orpheus pipeline modules.

Defined here (not in ``rag_pipeline.py``) to avoid circular imports between
the sub-pipeline modules and the facade orchestrator.

Backward-compatible re-exports remain in ``rag_pipeline.py``::

    from app.pipeline.rag_pipeline import IngestionResult, QueryResult  # still works
    from app.pipeline.models import IngestionResult, QueryResult         # preferred
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.augmentation.prompt_builder import AugmentedPrompt, CitationInfo
from app.generation.generator import GenerationResult
from app.pipeline.events import PipelineEvent
from app.retrieval.retriever import RetrievedChunk


@dataclass
class IngestionResult:
    """Full summary of a document ingestion run."""

    doc_id: str
    filename: str
    file_type: str
    total_chars: int
    page_count: int
    chunk_count: int
    total_tokens_estimate: int
    duration_ms: float
    events: List[PipelineEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "total_chars": self.total_chars,
            "page_count": self.page_count,
            "chunk_count": self.chunk_count,
            "total_tokens_estimate": self.total_tokens_estimate,
            "duration_ms": round(self.duration_ms, 2),
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class QueryResult:
    """Full summary of a question answering run."""

    query: str
    answer: str
    retrieved_chunks: List[RetrievedChunk]
    citations: List[CitationInfo]
    prompt: AugmentedPrompt
    generation: GenerationResult
    has_relevant_context: bool
    is_refusal: bool
    duration_ms: float
    events: List[PipelineEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "retrieved_chunks": [c.to_dict() for c in self.retrieved_chunks],
            "citations": [c.to_dict() for c in self.citations],
            "prompt": self.prompt.to_dict(),
            "generation": self.generation.to_dict(),
            "has_relevant_context": self.has_relevant_context,
            "is_refusal": self.is_refusal,
            "duration_ms": round(self.duration_ms, 2),
            "events": [e.to_dict() for e in self.events],
        }
