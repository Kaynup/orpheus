"""Unit tests for OfflineGroundedGenerator — no LLM, no vector store required."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.generation.offline_generator import OfflineGroundedGenerator


def _make_prompt(citations: dict, context: str, query: str):
    """Build a minimal AugmentedPrompt mock."""
    p = MagicMock()
    p.citations_map = citations
    p.formatted_context = context
    p.user_query = query
    p.full_prompt_text = f"SYSTEM\nUSER: {query}\nCONTEXT: {context}"
    return p


def _cit(snippet: str, filename: str = "doc.txt"):
    cit = MagicMock()
    cit.snippet = snippet
    cit.filename = filename
    return cit


class TestOfflineGroundedGenerator:
    def setup_method(self):
        self.gen = OfflineGroundedGenerator(topic_threshold=0.4, max_sentences=4)

    def test_refusal_on_no_citations(self):
        """Empty citations_map → refusal."""
        prompt = _make_prompt({}, "[NO RELEVANT CONTEXT FOUND]", "What is the policy?")
        result = self.gen.generate(prompt, time.perf_counter())
        assert result.is_refusal is True
        assert result.is_offline_mode is True
        assert result.model == "offline-grounded-fallback"

    def test_refusal_on_no_matching_sentences(self):
        """Context present but no query term in any sentence → refusal."""
        cit = _cit("The sky is blue and clouds are white.")
        prompt = _make_prompt({1: cit}, "The sky is blue and clouds are white.", "core collaboration hours")
        result = self.gen.generate(prompt, time.perf_counter())
        assert result.is_refusal is True

    def test_grounded_answer_returned(self):
        """When query topic words match sentences, return a grounded extractive answer."""
        cit = _cit("Core collaboration hours are from 10:00 AM to 3:00 PM Eastern Time.", "hr_policy.txt")
        context = "Core collaboration hours are from 10:00 AM to 3:00 PM Eastern Time."
        prompt = _make_prompt({1: cit}, context, "What are the core collaboration hours?")
        result = self.gen.generate(prompt, time.perf_counter())
        assert result.is_refusal is False
        assert "10:00" in result.answer or "collaboration" in result.answer
        assert len(result.citations) == 1

    def test_max_sentences_respected(self):
        """Generator should not return more sentences than max_sentences."""
        gen = OfflineGroundedGenerator(topic_threshold=0.0, max_sentences=2)
        snippet = "Topic one. Topic two. Topic three. Topic four. Topic five."
        cit = _cit(snippet, "doc.txt")
        context = snippet
        # Query word 'topic' appears in every sentence
        prompt = _make_prompt({1: cit}, context, "Tell me about topic")
        result = gen.generate(prompt, time.perf_counter())
        # Each sentence that matched topic becomes one entry
        sentence_count = result.answer.count("[Source")
        assert sentence_count <= 2
