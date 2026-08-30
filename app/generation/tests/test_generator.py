"""Unit tests for LLMGenerator, offline fallback extraction, NLP assets, and telemetry."""

import pytest

from app.augmentation.prompt_builder import AugmentedPrompt, CitationInfo
from app.config import LLMConfig
from app.generation.assets import ANCHOR_TERMS, DEFAULT_REFUSAL_TEXT, STOPWORDS, _load_json_asset
from app.generation.generator import (
    GenerationResult,
    LLMGenerator,
)


@pytest.fixture
def offline_generator():
    cfg = LLMConfig(
        model="offline",
        suppress_debug_info=True,
        offline_topic_threshold=0.4,
        offline_max_sentences=2,
    )
    return LLMGenerator(llm_config=cfg)


def test_generator_telemetry_configuration():
    """Verify LiteLLM telemetry toggle matches dynamic LLM configuration."""
    gen = LLMGenerator()
    import litellm

    assert litellm.suppress_debug_info == getattr(gen.config, "suppress_debug_info", True)


def test_load_json_asset_fail_fast(tmp_path):
    """Verify _load_json_asset raises FileNotFoundError when JSON asset does not exist."""
    missing_path = tmp_path / "missing_config.json"
    with pytest.raises(FileNotFoundError, match="Configuration asset file not found"):
        _load_json_asset(missing_path)


def test_nlp_assets_loaded_successfully():
    """Verify externalized stopwords and anchor terms are non-empty sets."""
    assert len(STOPWORDS) > 0
    assert len(ANCHOR_TERMS) > 0
    assert "the" in STOPWORDS or "what" in STOPWORDS
    assert "acme" in ANCHOR_TERMS or "company" in ANCHOR_TERMS or "document" in ANCHOR_TERMS


def test_generator_offline_refusal_on_empty_context(offline_generator):
    """Verify offline generator returns default refusal when no relevant context is present."""
    prompt = AugmentedPrompt(
        system_instruction="System prompt",
        formatted_context="[NO RELEVANT CONTEXT FOUND]",
        user_query="What is the meaning of life?",
        full_prompt_text="Prompt text",
        citations_map={},
        chunk_count=0,
    )

    result: GenerationResult = offline_generator.generate(prompt)
    assert result.is_refusal is True
    assert result.is_offline_mode is True
    assert result.answer == DEFAULT_REFUSAL_TEXT
    assert len(result.citations) == 0


def test_generator_offline_refusal_on_unmatched_topics(offline_generator):
    """Verify offline generator triggers refusal when topic keywords are missing in context."""
    citations = {
        1: CitationInfo(
            source_index=1,
            filename="cloud.txt",
            page_number=1,
            chunk_id="c1",
            similarity=0.8,
            snippet="Redis caching TTL is configured for 15 minutes.",
        )
    }
    prompt = AugmentedPrompt(
        system_instruction="System prompt",
        formatted_context="--- [Source 1: cloud.txt (Page 1)] ---\nRedis caching TTL is configured for 15 minutes.",
        user_query="What is the recipe for chocolate cake and frosting?",
        full_prompt_text="Full prompt text",
        citations_map=citations,
        chunk_count=1,
    )

    result: GenerationResult = offline_generator.generate(prompt)
    assert result.is_refusal is True
    assert result.is_offline_mode is True
    assert result.answer == DEFAULT_REFUSAL_TEXT


def test_generator_offline_extractive_grounding_and_sentence_limit(offline_generator):
    """Verify offline generator extracts matching sentences and respects offline_max_sentences limit."""
    citations = {
        1: CitationInfo(
            source_index=1,
            filename="acme_policy.txt",
            page_number=1,
            chunk_id="c1",
            similarity=0.9,
            snippet=(
                "Core hours are 10:00 AM to 3:00 PM. Stipend is $750. "
                "In-office days are Tuesdays and Thursdays. Vacation is 20 days."
            ),
        )
    }
    context_text = (
        "--- [Source 1: acme_policy.txt (Page 1)] ---\n"
        "Core hours are 10:00 AM to 3:00 PM. "
        "Stipend is $750 for home equipment. "
        "In-office days are Tuesdays and Thursdays. "
        "Vacation is 20 days per year."
    )
    prompt = AugmentedPrompt(
        system_instruction="System prompt",
        formatted_context=context_text,
        user_query="What are the core hours and stipend for home equipment?",
        full_prompt_text="Full prompt text",
        citations_map=citations,
        chunk_count=1,
    )

    result: GenerationResult = offline_generator.generate(prompt)
    assert result.is_refusal is False
    assert result.is_offline_mode is True
    assert "10:00 AM to 3:00 PM" in result.answer or "$750" in result.answer
    assert "[Source 1" in result.answer
    assert len(result.citations) == 1

    # Sentence limit check: max 2 sentences configured in fixture
    import re

    clean_text = re.sub(r"\[Source[^\]]+\]", "", result.answer).strip()
    raw_sentences = [s.strip() for s in clean_text.split(".") if s.strip()]
    assert len(raw_sentences) <= offline_generator.config.offline_max_sentences


def test_generation_result_to_dict():
    """Verify GenerationResult dictionary serialization."""
    cit = [
        CitationInfo(
            source_index=1,
            filename="doc.txt",
            page_number=1,
            chunk_id="chk1",
            similarity=0.85,
            snippet="Sample snippet",
        )
    ]
    res = GenerationResult(
        answer="Grounded answer text [Source 1]",
        model="offline-grounded-fallback",
        latency_ms=12.5,
        prompt_tokens=50,
        completion_tokens=10,
        total_tokens=60,
        citations=cit,
        is_refusal=False,
        is_offline_mode=True,
    )
    d = res.to_dict()
    assert d["answer"] == "Grounded answer text [Source 1]"
    assert d["model"] == "offline-grounded-fallback"
    assert d["latency_ms"] == 12.5
    assert d["total_tokens"] == 60
    assert len(d["citations"]) == 1
    assert d["is_refusal"] is False
    assert d["is_offline_mode"] is True
