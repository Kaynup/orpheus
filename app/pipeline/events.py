"""Real-time pipeline event models for truthful backend-to-frontend state synchronization."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional


class EventStage(str, Enum):
    # Ingestion Pipeline Stages
    DOC_RECEIVED = "DOC_RECEIVED"
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    CHUNKS_CREATED = "CHUNKS_CREATED"
    EMBEDDINGS_GENERATED = "EMBEDDINGS_GENERATED"
    VECTORS_STORED = "VECTORS_STORED"
    INDEXING_COMPLETE = "INDEXING_COMPLETE"

    # Query Pipeline Stages
    QUERY_RECEIVED = "QUERY_RECEIVED"
    QUERY_EMBEDDED = "QUERY_EMBEDDED"
    RETRIEVING_CHUNKS = "RETRIEVING_CHUNKS"
    CONTEXT_SELECTED = "CONTEXT_SELECTED"
    PROMPT_PREPARED = "PROMPT_PREPARED"
    GENERATING_ANSWER = "GENERATING_ANSWER"
    ANSWER_COMPLETE = "ANSWER_COMPLETE"

    # General
    PIPELINE_FAILED = "PIPELINE_FAILED"


class EventStatus(str, Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class PipelineEvent:
    """Represents an atomic backend state transition event."""
    stage: EventStage
    status: EventStatus
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


# Callback signature for event listeners
EventCallback = Callable[[PipelineEvent], None]
