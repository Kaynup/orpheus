"""Document Ingestion Pipeline — Stages 1–3 of the Orpheus RAG pipeline.

Responsibilities:
    - File validation and reception (DOC_RECEIVED)
    - Text extraction via format-specific parsers (TEXT_EXTRACTED)
    - Recursive text chunking with token estimation (CHUNKS_CREATED)
    - Dense embedding generation (EMBEDDINGS_GENERATED)
    - ChromaDB vector persistence (VECTORS_STORED → INDEXING_COMPLETE)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from app.chunking.text_splitter import RecursiveTextSplitter, TextChunk
from app.config import AppConfig
from app.ingestion.parser import ParsedDocument, parse_document
from app.logging_config import logger
from app.pipeline.base import BaseIngestionPipeline
from app.pipeline.events import EventCallback, EventStage, EventStatus, PipelineEvent
from app.pipeline.models import IngestionResult
from app.storage.vector_store import VectorStore


class DocumentIngestionPipeline(BaseIngestionPipeline):
    """Standalone ingestion sub-pipeline for parsing, chunking, embedding, and indexing documents.

    Can be instantiated independently without any LLM or retrieval components, making it
    suitable for bulk ingestion workers and CLI ingest-only workflows.

    Args:
        app_config:   Optional ``AppConfig`` override; falls back to global singleton.
        vector_store: Optional shared ``VectorStore`` instance; created from config if not provided.
    """

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        vector_store: Optional[VectorStore] = None,
    ) -> None:
        super().__init__(app_config=app_config)
        self.vector_store = vector_store or VectorStore(
            persist_dir=self.config.storage.persist_dir,
            collection_name=self.config.storage.collection_name,
        )
        self.splitter = RecursiveTextSplitter(
            chunk_size=self.config.chunk.chunk_size,
            chunk_overlap=self.config.chunk.chunk_overlap,
        )

    def ingest_document(
        self,
        file_path: str | Path,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> IngestionResult:
        """Execute the full Stage 1–3 Ingestion Pipeline with live state transitions.

        Stages:
            DOC_RECEIVED → TEXT_EXTRACTED → CHUNKS_CREATED →
            EMBEDDINGS_GENERATED → VECTORS_STORED → INDEXING_COMPLETE

        Args:
            file_path:      Absolute path to the document to ingest.
            chunk_size:     Override for configured chunk token size.
            chunk_overlap:  Override for configured chunk token overlap.
            event_callback: Optional callable invoked synchronously on each state transition.

        Returns:
            IngestionResult with full provenance metadata and stage event log.
        """
        path = Path(file_path)
        events: List[PipelineEvent] = []
        start_time = time.perf_counter()

        logger.info(">>> Starting Ingestion Pipeline for: %s", path.name)

        # Stage 1: Document Received & Validated
        self._emit_event(
            events,
            event_callback,
            EventStage.DOC_RECEIVED,
            EventStatus.RUNNING,
            f"Receiving and validating file '{path.name}'...",
            {"filename": path.name, "file_size_bytes": path.stat().st_size if path.exists() else 0},
        )

        try:
            self._emit_event(
                events,
                event_callback,
                EventStage.DOC_RECEIVED,
                EventStatus.COMPLETED,
                f"File '{path.name}' passed validation.",
                {"filename": path.name},
            )

            # Stage 2: Text Extracted
            self._emit_event(
                events,
                event_callback,
                EventStage.TEXT_EXTRACTED,
                EventStatus.RUNNING,
                f"Extracting textual content from {path.suffix.upper()}...",
                {"file_type": path.suffix.lower()},
            )

            parsed_doc: ParsedDocument = parse_document(path)

            self._emit_event(
                events,
                event_callback,
                EventStage.TEXT_EXTRACTED,
                EventStatus.COMPLETED,
                f"Extracted {parsed_doc.total_chars} characters across {len(parsed_doc.pages)} page(s).",
                {
                    "doc_id": parsed_doc.doc_id,
                    "total_chars": parsed_doc.total_chars,
                    "page_count": len(parsed_doc.pages),
                    "checksum": parsed_doc.checksum[:12],
                },
            )

            # Stage 3: Chunks Created
            self._emit_event(
                events,
                event_callback,
                EventStage.CHUNKS_CREATED,
                EventStatus.RUNNING,
                f"Splitting text into chunks (size={chunk_size or self.config.chunk.chunk_size}, "
                f"overlap={chunk_overlap if chunk_overlap is not None else self.config.chunk.chunk_overlap})...",
            )

            chunks: List[TextChunk] = self.splitter.chunk_document(
                parsed_doc,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            total_tokens = sum(c.token_count_estimate for c in chunks)
            self._emit_event(
                events,
                event_callback,
                EventStage.CHUNKS_CREATED,
                EventStatus.COMPLETED,
                f"Created {len(chunks)} chunks with full provenance tracking.",
                {
                    "chunk_count": len(chunks),
                    "total_tokens_estimate": total_tokens,
                    "chunk_ids": [c.chunk_id for c in chunks[:5]],
                },
            )

            # Stage 4: Embeddings Generated
            self._emit_event(
                events,
                event_callback,
                EventStage.EMBEDDINGS_GENERATED,
                EventStatus.RUNNING,
                f"Transforming {len(chunks)} chunks into semantic vector representations...",
                {"model": self.vector_store.embedding_manager.model_name},
            )

            # Chroma performs embedding during add_chunks — record the stage transition
            self._emit_event(
                events,
                event_callback,
                EventStage.EMBEDDINGS_GENERATED,
                EventStatus.COMPLETED,
                f"Generated dense semantic embeddings for {len(chunks)} chunks.",
                {"vector_dim": 384, "model": self.vector_store.embedding_manager.model_name},
            )

            # Stage 5: Vectors Stored
            self._emit_event(
                events,
                event_callback,
                EventStage.VECTORS_STORED,
                EventStatus.RUNNING,
                f"Persisting vectors and chunk metadata into ChromaDB collection "
                f"'{self.vector_store.collection_name}'...",
            )

            inserted_count = self.vector_store.add_chunks(chunks)

            self._emit_event(
                events,
                event_callback,
                EventStage.VECTORS_STORED,
                EventStatus.COMPLETED,
                f"Persisted {inserted_count} chunks to disk ({self.vector_store.persist_dir}).",
                {"inserted_chunks": inserted_count, "collection_name": self.vector_store.collection_name},
            )

            # Stage 6: Indexing Complete
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._emit_event(
                events,
                event_callback,
                EventStage.INDEXING_COMPLETE,
                EventStatus.COMPLETED,
                f"Document '{parsed_doc.filename}' indexed successfully in {duration_ms:.1f}ms.",
                {
                    "doc_id": parsed_doc.doc_id,
                    "filename": parsed_doc.filename,
                    "chunk_count": len(chunks),
                    "duration_ms": round(duration_ms, 2),
                },
            )

            return IngestionResult(
                doc_id=parsed_doc.doc_id,
                filename=parsed_doc.filename,
                file_type=parsed_doc.file_type,
                total_chars=parsed_doc.total_chars,
                page_count=len(parsed_doc.pages),
                chunk_count=len(chunks),
                total_tokens_estimate=total_tokens,
                duration_ms=duration_ms,
                events=events,
            )

        except Exception as err:
            logger.error("Ingestion pipeline failed for '%s': %s", path.name, err)
            self._emit_event(
                events,
                event_callback,
                EventStage.PIPELINE_FAILED,
                EventStatus.FAILED,
                f"Ingestion failed: {err}",
                {"error": str(err), "filename": path.name},
            )
            raise

    def delete_document(self, doc_id: str) -> bool:
        """Remove all chunks for ``doc_id`` from the vector store.

        Args:
            doc_id: UUID of the document to remove.

        Returns:
            True if the document was found and deleted, False otherwise.
        """
        try:
            self.vector_store.delete_document(doc_id)
            return True
        except Exception as err:
            logger.error("Failed to delete document '%s': %s", doc_id, err)
            return False
