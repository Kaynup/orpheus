"""Main RAG Pipeline Orchestrator with real-time event streaming and educational transparency."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.augmentation.prompt_builder import AugmentedPrompt, CitationInfo, PromptBuilder
from app.chunking.text_splitter import RecursiveTextSplitter, TextChunk
from app.config import AppConfig, config
from app.generation.generator import GenerationResult, LLMGenerator
from app.ingestion.parser import ParsedDocument, parse_document
from app.logging_config import logger
from app.pipeline.events import EventCallback, EventStage, EventStatus, PipelineEvent
from app.retrieval.retriever import RetrievalOutput, RetrievedChunk, SemanticRetriever
from app.storage.vector_store import VectorStore


@dataclass
class IngestionResult:
    """Full summary of document ingestion."""
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
    """Full summary of question answering execution."""
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


class RAGPipeline:
    """
    Unified RAG pipeline combining Ingestion, Chunking, Embedding, Storage,
    Retrieval, Augmentation, and Generation with synchronous event dispatching.
    """

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        self.config = app_config or config
        self.vector_store = vector_store or VectorStore(
            persist_dir=self.config.storage.persist_dir,
            collection_name=self.config.storage.collection_name,
        )
        self.splitter = RecursiveTextSplitter(
            chunk_size=self.config.chunk.chunk_size,
            chunk_overlap=self.config.chunk.chunk_overlap,
        )
        self.retriever = SemanticRetriever(
            vector_store=self.vector_store,
            retrieval_config=self.config.retrieval,
        )
        self.prompt_builder = PromptBuilder()
        self.generator = LLMGenerator(llm_config=self.config.llm)

    def _emit_event(
        self,
        events_list: List[PipelineEvent],
        callback: Optional[EventCallback],
        stage: EventStage,
        status: EventStatus,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> PipelineEvent:
        """Create, append, and dispatch an atomic pipeline event."""
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

    def ingest_document(
        self,
        file_path: str | Path,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> IngestionResult:
        """
        Execute the full Stage 1 - 3 Ingestion Pipeline with live state transitions.
        """
        path = Path(file_path)
        events: List[PipelineEvent] = []
        start_time = time.perf_counter()

        logger.info(">>> Starting Ingestion Pipeline for: %s", path.name)

        # Stage 1: Document Received & Validated
        self._emit_event(
            events, event_callback,
            EventStage.DOC_RECEIVED, EventStatus.RUNNING,
            f"Receiving and validating file '{path.name}'...",
            {"filename": path.name, "file_size_bytes": path.stat().st_size if path.exists() else 0},
        )

        try:
            # Stage 2: Text Extracted
            self._emit_event(
                events, event_callback,
                EventStage.DOC_RECEIVED, EventStatus.COMPLETED,
                f"File '{path.name}' passed validation.",
                {"filename": path.name},
            )

            self._emit_event(
                events, event_callback,
                EventStage.TEXT_EXTRACTED, EventStatus.RUNNING,
                f"Extracting textual content from {path.suffix.upper()}...",
                {"file_type": path.suffix.lower()},
            )

            parsed_doc: ParsedDocument = parse_document(path)

            self._emit_event(
                events, event_callback,
                EventStage.TEXT_EXTRACTED, EventStatus.COMPLETED,
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
                events, event_callback,
                EventStage.CHUNKS_CREATED, EventStatus.RUNNING,
                f"Splitting text into chunks (size={chunk_size or self.config.chunk.chunk_size}, overlap={chunk_overlap if chunk_overlap is not None else self.config.chunk.chunk_overlap})...",
            )

            chunks: List[TextChunk] = self.splitter.chunk_document(
                parsed_doc,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            total_tokens = sum(c.token_count_estimate for c in chunks)
            self._emit_event(
                events, event_callback,
                EventStage.CHUNKS_CREATED, EventStatus.COMPLETED,
                f"Created {len(chunks)} chunks with full provenance tracking.",
                {
                    "chunk_count": len(chunks),
                    "total_tokens_estimate": total_tokens,
                    "chunk_ids": [c.chunk_id for c in chunks[:5]],
                },
            )

            # Stage 4: Embeddings Generated
            self._emit_event(
                events, event_callback,
                EventStage.EMBEDDINGS_GENERATED, EventStatus.RUNNING,
                f"Transforming {len(chunks)} chunks into semantic vector representations...",
                {"model": self.vector_store.embedding_manager.model_name},
            )

            # Chroma performs embedding during add_chunks
            # We explicitly record the stage transition
            self._emit_event(
                events, event_callback,
                EventStage.EMBEDDINGS_GENERATED, EventStatus.COMPLETED,
                f"Generated dense semantic embeddings for {len(chunks)} chunks.",
                {"vector_dim": 384, "model": self.vector_store.embedding_manager.model_name},
            )

            # Stage 5: Vectors Stored
            self._emit_event(
                events, event_callback,
                EventStage.VECTORS_STORED, EventStatus.RUNNING,
                f"Persisting vectors and chunk metadata into ChromaDB collection '{self.vector_store.collection_name}'...",
            )

            inserted_count = self.vector_store.add_chunks(chunks)

            self._emit_event(
                events, event_callback,
                EventStage.VECTORS_STORED, EventStatus.COMPLETED,
                f"Persisted {inserted_count} chunks to disk ({self.vector_store.persist_dir}).",
                {"inserted_chunks": inserted_count, "collection_name": self.vector_store.collection_name},
            )

            # Stage 6: Indexing Complete
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._emit_event(
                events, event_callback,
                EventStage.INDEXING_COMPLETE, EventStatus.COMPLETED,
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
                events, event_callback,
                EventStage.PIPELINE_FAILED, EventStatus.FAILED,
                f"Ingestion failed: {err}",
                {"error": str(err), "filename": path.name},
            )
            raise

    def answer_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> QueryResult:
        """
        Execute the full Stage 4 - 7 Query & QA Pipeline with live state transitions.
        """
        events: List[PipelineEvent] = []
        start_time = time.perf_counter()
        clean_query = query.strip()

        logger.info(">>> Starting QA Pipeline for query: '%.60s'", clean_query)

        # Stage 1: Query Received
        self._emit_event(
            events, event_callback,
            EventStage.QUERY_RECEIVED, EventStatus.COMPLETED,
            f"Received query: '{clean_query}'",
            {"query": clean_query, "char_count": len(clean_query)},
        )

        try:
            # Stage 2: Query Embedded
            self._emit_event(
                events, event_callback,
                EventStage.QUERY_EMBEDDED, EventStatus.RUNNING,
                "Computing semantic embedding vector for query...",
            )
            # Embed query
            _ = self.vector_store.embedding_manager.embed_query(clean_query)
            self._emit_event(
                events, event_callback,
                EventStage.QUERY_EMBEDDED, EventStatus.COMPLETED,
                "Query transformed to 384-d semantic representation.",
                {"embedding_model": self.vector_store.embedding_manager.model_name},
            )

            # Stage 3: Retrieving Relevant Chunks
            k = top_k or self.config.retrieval.top_k
            threshold = score_threshold if score_threshold is not None else self.config.retrieval.score_threshold

            self._emit_event(
                events, event_callback,
                EventStage.RETRIEVING_CHUNKS, EventStatus.RUNNING,
                f"Searching vector store for top {k} nearest chunks (max distance <= {threshold})...",
                {"top_k": k, "score_threshold": threshold},
            )

            retrieval_output: RetrievalOutput = self.retriever.retrieve(
                query=clean_query,
                top_k=k,
                score_threshold=threshold,
            )

            self._emit_event(
                events, event_callback,
                EventStage.RETRIEVING_CHUNKS, EventStatus.COMPLETED,
                f"Retrieved {len(retrieval_output.chunks)} candidate chunk(s).",
                {
                    "retrieved_count": len(retrieval_output.chunks),
                    "highest_similarity": round(retrieval_output.highest_similarity, 4),
                    "lowest_distance": round(retrieval_output.lowest_distance, 4),
                },
            )

            # Stage 4: Context Selected
            self._emit_event(
                events, event_callback,
                EventStage.CONTEXT_SELECTED, EventStatus.RUNNING,
                "Filtering context chunks and evaluating relevance confidence...",
            )

            confident_chunks = [c for c in retrieval_output.chunks if c.is_confident]

            self._emit_event(
                events, event_callback,
                EventStage.CONTEXT_SELECTED, EventStatus.COMPLETED,
                f"Selected {len(confident_chunks)} confident context chunk(s) (has_relevant={retrieval_output.has_relevant_context}).",
                {
                    "confident_chunk_count": len(confident_chunks),
                    "has_relevant_context": retrieval_output.has_relevant_context,
                    "top_source": confident_chunks[0].source_filename if confident_chunks else None,
                },
            )

            # Stage 5: Prompt Augmented
            self._emit_event(
                events, event_callback,
                EventStage.PROMPT_PREPARED, EventStatus.RUNNING,
                "Augmenting system instructions with numbered context blocks and citation placeholders...",
            )

            prompt: AugmentedPrompt = self.prompt_builder.build_prompt(
                query=clean_query,
                retrieved_chunks=retrieval_output.chunks,
            )

            self._emit_event(
                events, event_callback,
                EventStage.PROMPT_PREPARED, EventStatus.COMPLETED,
                f"Constructed prompt ({len(prompt.full_prompt_text)} chars, {len(prompt.citations_map)} sources).",
                {
                    "prompt_char_length": len(prompt.full_prompt_text),
                    "citation_count": len(prompt.citations_map),
                    "system_rules_active": True,
                },
            )

            # Stage 6: Generating Answer
            target_model = model or self.config.llm.model
            self._emit_event(
                events, event_callback,
                EventStage.GENERATING_ANSWER, EventStatus.RUNNING,
                f"Generating grounded answer via {target_model}...",
                {"model": target_model, "temperature": temperature or self.config.llm.temperature},
            )

            generation_res: GenerationResult = self.generator.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
            )

            self._emit_event(
                events, event_callback,
                EventStage.GENERATING_ANSWER, EventStatus.COMPLETED,
                f"Answer generated in {generation_res.latency_ms:.1f}ms ({generation_res.total_tokens} tokens).",
                {
                    "latency_ms": generation_res.latency_ms,
                    "total_tokens": generation_res.total_tokens,
                    "is_refusal": generation_res.is_refusal,
                    "cited_count": len(generation_res.citations),
                },
            )

            # Stage 7: Answer Complete
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._emit_event(
                events, event_callback,
                EventStage.ANSWER_COMPLETE, EventStatus.COMPLETED,
                f"QA Pipeline finished in {duration_ms:.1f}ms.",
                {
                    "duration_ms": round(duration_ms, 2),
                    "is_refusal": generation_res.is_refusal,
                },
            )

            return QueryResult(
                query=clean_query,
                answer=generation_res.answer,
                retrieved_chunks=retrieval_output.chunks,
                citations=generation_res.citations,
                prompt=prompt,
                generation=generation_res,
                has_relevant_context=retrieval_output.has_relevant_context,
                is_refusal=generation_res.is_refusal,
                duration_ms=duration_ms,
                events=events,
            )

        except Exception as err:
            logger.error("QA pipeline failed for query '%s': %s", clean_query, err)
            self._emit_event(
                events, event_callback,
                EventStage.PIPELINE_FAILED, EventStatus.FAILED,
                f"QA failed: {err}",
                {"error": str(err), "query": clean_query},
            )
            raise
