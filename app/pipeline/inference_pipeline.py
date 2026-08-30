"""Query Inference Pipeline — Stages 4–7 of the Orpheus RAG pipeline.

Responsibilities:
    - Query embedding (QUERY_EMBEDDED)
    - Semantic k-NN retrieval with confidence scoring (RETRIEVING_CHUNKS)
    - Context selection and relevance filtering (CONTEXT_SELECTED)
    - Retrieval-augmented prompt construction (PROMPT_PREPARED)
    - Grounded LLM answer generation with citation provenance (GENERATING_ANSWER → ANSWER_COMPLETE)
"""

from __future__ import annotations

import time
from typing import List, Optional

from app.augmentation.prompt_builder import AugmentedPrompt, PromptBuilder
from app.config import AppConfig
from app.generation.generator import GenerationResult, LLMGenerator
from app.logging_config import logger
from app.pipeline.base import BaseInferencePipeline
from app.pipeline.events import EventCallback, EventStage, EventStatus, PipelineEvent
from app.pipeline.models import QueryResult
from app.retrieval.retriever import RetrievalOutput, SemanticRetriever
from app.storage.vector_store import VectorStore


class QueryInferencePipeline(BaseInferencePipeline):
    """Standalone inference sub-pipeline for semantic retrieval and grounded answer generation.

    Can be instantiated independently of ingestion components. It requires only a populated
    ``VectorStore`` to operate, making it suitable for read-only query workers and evaluation runs.

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
        self.retriever = SemanticRetriever(
            vector_store=self.vector_store,
            retrieval_config=self.config.retrieval,
        )
        self.prompt_builder = PromptBuilder()
        self.generator = LLMGenerator(llm_config=self.config.llm)

    def answer_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> QueryResult:
        """Execute the full Stage 4–7 Query & QA Pipeline with live state transitions.

        Stages:
            QUERY_RECEIVED → QUERY_EMBEDDED → RETRIEVING_CHUNKS →
            CONTEXT_SELECTED → PROMPT_PREPARED → GENERATING_ANSWER → ANSWER_COMPLETE

        Args:
            query:            Raw natural language query string.
            top_k:            Override for configured retrieval candidate count.
            score_threshold:  Override for configured relevance confidence threshold.
            model:            Override for configured LLM model identifier.
            temperature:      Override for configured LLM sampling temperature.
            event_callback:   Optional callable invoked synchronously on each state transition.

        Returns:
            QueryResult with grounded answer, citations, retrieved chunks, and stage event log.
        """
        events: List[PipelineEvent] = []
        start_time = time.perf_counter()
        clean_query = query.strip()

        logger.info(">>> Starting QA Pipeline for query: '%.60s'", clean_query)

        # Stage 1: Query Received
        self._emit_event(
            events,
            event_callback,
            EventStage.QUERY_RECEIVED,
            EventStatus.COMPLETED,
            f"Received query: '{clean_query}'",
            {"query": clean_query, "char_count": len(clean_query)},
        )

        try:
            # Stage 2: Query Embedded
            self._emit_event(
                events,
                event_callback,
                EventStage.QUERY_EMBEDDED,
                EventStatus.RUNNING,
                "Computing semantic embedding vector for query...",
            )
            _ = self.vector_store.embedding_manager.embed_query(clean_query)
            self._emit_event(
                events,
                event_callback,
                EventStage.QUERY_EMBEDDED,
                EventStatus.COMPLETED,
                "Query transformed to 384-d semantic representation.",
                {"embedding_model": self.vector_store.embedding_manager.model_name},
            )

            # Stage 3: Retrieving Relevant Chunks
            k = top_k or self.config.retrieval.top_k
            threshold = score_threshold if score_threshold is not None else self.config.retrieval.score_threshold

            self._emit_event(
                events,
                event_callback,
                EventStage.RETRIEVING_CHUNKS,
                EventStatus.RUNNING,
                f"Searching vector store for top {k} nearest chunks (max distance <= {threshold})...",
                {"top_k": k, "score_threshold": threshold},
            )

            retrieval_output: RetrievalOutput = self.retriever.retrieve(
                query=clean_query,
                top_k=k,
                score_threshold=threshold,
            )

            self._emit_event(
                events,
                event_callback,
                EventStage.RETRIEVING_CHUNKS,
                EventStatus.COMPLETED,
                f"Retrieved {len(retrieval_output.chunks)} candidate chunk(s).",
                {
                    "retrieved_count": len(retrieval_output.chunks),
                    "highest_similarity": round(retrieval_output.highest_similarity, 4),
                    "lowest_distance": round(retrieval_output.lowest_distance, 4),
                },
            )

            # Stage 4: Context Selected
            self._emit_event(
                events,
                event_callback,
                EventStage.CONTEXT_SELECTED,
                EventStatus.RUNNING,
                "Filtering context chunks and evaluating relevance confidence...",
            )

            confident_chunks = [c for c in retrieval_output.chunks if c.is_confident]

            self._emit_event(
                events,
                event_callback,
                EventStage.CONTEXT_SELECTED,
                EventStatus.COMPLETED,
                f"Selected {len(confident_chunks)} confident context chunk(s) "
                f"(has_relevant={retrieval_output.has_relevant_context}).",
                {
                    "confident_chunk_count": len(confident_chunks),
                    "has_relevant_context": retrieval_output.has_relevant_context,
                    "top_source": confident_chunks[0].source_filename if confident_chunks else None,
                },
            )

            # Stage 5: Prompt Augmented
            self._emit_event(
                events,
                event_callback,
                EventStage.PROMPT_PREPARED,
                EventStatus.RUNNING,
                "Augmenting system instructions with numbered context blocks and citation placeholders...",
            )

            prompt: AugmentedPrompt = self.prompt_builder.build_prompt(
                query=clean_query,
                retrieved_chunks=retrieval_output.chunks,
            )

            self._emit_event(
                events,
                event_callback,
                EventStage.PROMPT_PREPARED,
                EventStatus.COMPLETED,
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
                events,
                event_callback,
                EventStage.GENERATING_ANSWER,
                EventStatus.RUNNING,
                f"Generating grounded answer via {target_model}...",
                {"model": target_model, "temperature": temperature or self.config.llm.temperature},
            )

            generation_res: GenerationResult = self.generator.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
            )

            self._emit_event(
                events,
                event_callback,
                EventStage.GENERATING_ANSWER,
                EventStatus.COMPLETED,
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
                events,
                event_callback,
                EventStage.ANSWER_COMPLETE,
                EventStatus.COMPLETED,
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
                events,
                event_callback,
                EventStage.PIPELINE_FAILED,
                EventStatus.FAILED,
                f"QA failed: {err}",
                {"error": str(err), "query": clean_query},
            )
            raise
