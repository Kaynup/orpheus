"""Offline extractive fallback generator — grounded, keyless, deterministic.

``OfflineGroundedGenerator`` implements a purely extractive answer strategy that:

1. Refuses if the retrieved context contains no citations or no relevant topic words.
2. Matches query topic words against sentence-level text in each retrieved citation.
3. Assembles a concise, source-attributed answer from the top matching sentences.

This class carries no LLM dependencies and can be unit-tested without any API
credentials or vector-store fixtures.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List

from app.generation.assets import ANCHOR_TERMS, DEFAULT_REFUSAL_TEXT, STOPWORDS
from app.logging_config import logger

if TYPE_CHECKING:
    from app.augmentation.prompt_builder import AugmentedPrompt, CitationInfo
    from app.generation.generator import GenerationResult


class OfflineGroundedGenerator:
    """Extracts a grounded answer from retrieved context without any LLM call.

    Args:
        topic_threshold: Minimum fraction of topic words that must be present in
            the combined context before generation is attempted.  Defaults to
            ``0.4`` (40 %).
        max_sentences: Maximum number of matching sentences to include in the
            assembled answer.  Defaults to ``4``.
    """

    def __init__(
        self,
        topic_threshold: float = 0.4,
        max_sentences: int = 4,
    ) -> None:
        self.topic_threshold = topic_threshold
        self.max_sentences = max_sentences

    # Public interface

    def generate(
        self,
        prompt: "AugmentedPrompt",
        start_time: float,
    ) -> "GenerationResult":
        """Produce a grounded extractive answer from *prompt* context.

        Returns a refusal ``GenerationResult`` when:
        - The context contains no retrieved citations.
        - Fewer than ``topic_threshold`` fraction of topic words are present.
        - No sentence from any citation matches any query term.
        """
        # Import here to avoid circular dependency at module load time
        from app.generation.generator import GenerationResult

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if not prompt.citations_map or prompt.formatted_context == "[NO RELEVANT CONTEXT FOUND]":
            logger.debug("Offline generator: no citations — refusing.")
            return self._refusal(elapsed_ms, prompt)

        topic_words, query_words = self._extract_query_words(prompt.user_query)
        all_context_lower = prompt.formatted_context.lower()

        # Topic-coverage gate
        if topic_words:
            matched = [tw for tw in topic_words if tw in all_context_lower]
            if len(matched) < max(1, len(topic_words) * self.topic_threshold):
                logger.debug(
                    "Offline generator: only %d/%d topic words matched — refusing.",
                    len(matched),
                    len(topic_words),
                )
                return self._refusal(elapsed_ms, prompt)

        matched_sentences, cited_sources = self._extract_sentences(
            prompt, topic_words or query_words
        )

        if not matched_sentences:
            logger.debug("Offline generator: no matching sentences — refusing.")
            return self._refusal(elapsed_ms, prompt)

        answer = " ".join(matched_sentences[: self.max_sentences])

        return GenerationResult(
            answer=answer,
            model="offline-grounded-fallback",
            latency_ms=elapsed_ms,
            prompt_tokens=len(prompt.full_prompt_text) // 4,
            completion_tokens=len(answer) // 4,
            total_tokens=(len(prompt.full_prompt_text) + len(answer)) // 4,
            citations=cited_sources,
            is_refusal=False,
            is_offline_mode=True,
        )

    # Private helpers

    def _extract_query_words(self, user_query: str) -> tuple[list[str], list[str]]:
        """Return (topic_words, all_query_words) filtered by stopwords and length."""
        raw_words = [
            w.lower().strip("?,!.:;\"'()")
            for w in user_query.split()
            if len(w.strip("?,!.:;\"'()")) >= 3
            and w.lower().strip("?,!.:;\"'()") not in STOPWORDS
        ]
        topic_words = [w for w in raw_words if w not in ANCHOR_TERMS]
        return topic_words, raw_words

    def _extract_sentences(
        self,
        prompt: "AugmentedPrompt",
        match_words: List[str],
    ) -> tuple[list[str], list["CitationInfo"]]:
        """Scan each citation's snippet for sentences containing query terms."""
        matched_sentences: list[str] = []
        cited_sources: list["CitationInfo"] = []

        for idx, cit in prompt.citations_map.items():
            raw_sentences = [s.strip() for s in cit.snippet.replace("\n", " ").split(". ") if s.strip()]
            for sentence in raw_sentences:
                sent_lower = sentence.lower()
                if any(qw in sent_lower for qw in match_words):
                    clean_sent = sentence.rstrip(".") + "."
                    matched_sentences.append(f"{clean_sent} [Source {idx}: {cit.filename}]")
                    if cit not in cited_sources:
                        cited_sources.append(cit)

        return matched_sentences, cited_sources

    def _refusal(self, elapsed_ms: float, prompt: "AugmentedPrompt") -> "GenerationResult":
        """Build a standard refusal GenerationResult."""
        from app.generation.generator import GenerationResult

        refusal_text = DEFAULT_REFUSAL_TEXT
        return GenerationResult(
            answer=refusal_text,
            model="offline-grounded-fallback",
            latency_ms=elapsed_ms,
            prompt_tokens=len(prompt.full_prompt_text) // 4,
            completion_tokens=len(refusal_text) // 4,
            total_tokens=(len(prompt.full_prompt_text) + len(refusal_text)) // 4,
            citations=[],
            is_refusal=True,
            is_offline_mode=True,
        )
