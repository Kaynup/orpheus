"""Unit tests for PromptBuilder, dynamic asset loading, and citation mapping."""

from pathlib import Path
import pytest

from app.augmentation.prompt_builder import (
    AugmentedPrompt,
    CitationInfo,
    PromptBuilder,
    _load_asset,
)
from app.retrieval.retriever import RetrievedChunk


@pytest.fixture
def sample_retrieved_chunks():
    return [
        RetrievedChunk(
            rank=1,
            chunk_id="chk_01",
            content="Acme Corporation operates on core hours from 10:00 AM to 3:00 PM ET.",
            doc_id="doc_hr",
            source_filename="acme_hr_policy.txt",
            page_number=1,
            chunk_index=0,
            distance=0.15,
            similarity=0.85,
            is_confident=True,
            metadata={"file_type": "txt"},
        ),
        RetrievedChunk(
            rank=2,
            chunk_id="chk_02",
            content="Employees receive a one-time home office equipment stipend of $750.",
            doc_id="doc_hr",
            source_filename="acme_hr_policy.txt",
            page_number=1,
            chunk_index=1,
            distance=0.25,
            similarity=0.75,
            is_confident=True,
            metadata={"file_type": "txt"},
        ),
    ]


def test_prompt_builder_asset_loading():
    """Verify PromptBuilder dynamically loads system instructions and user templates from assets."""
    builder = PromptBuilder()
    assert len(builder.system_instruction.strip()) > 0
    assert "{formatted_context}" in builder.query_template
    assert "{query}" in builder.query_template


def test_load_asset_missing_file_raises_filenotfound(tmp_path):
    """Verify _load_asset raises FileNotFoundError when target asset does not exist."""
    missing_path = tmp_path / "non_existent_prompt_template.txt"
    with pytest.raises(FileNotFoundError, match="Prompt asset file not found"):
        _load_asset(missing_path)


def test_prompt_builder_citation_mapping_and_indexing(sample_retrieved_chunks):
    """Verify build_prompt generates 1-indexed citation maps matching input chunks."""
    builder = PromptBuilder()
    query = "What is the equipment stipend and what are the core hours?"

    prompt = builder.build_prompt(query=query, retrieved_chunks=sample_retrieved_chunks)
    assert isinstance(prompt, AugmentedPrompt)
    assert prompt.user_query == query
    assert prompt.chunk_count == len(sample_retrieved_chunks)
    assert len(prompt.citations_map) == len(sample_retrieved_chunks)

    for idx, chunk in enumerate(sample_retrieved_chunks, start=1):
        assert idx in prompt.citations_map
        citation: CitationInfo = prompt.citations_map[idx]
        assert citation.source_index == idx
        assert citation.filename == chunk.source_filename
        assert citation.page_number == chunk.page_number
        assert citation.chunk_id == chunk.chunk_id
        assert citation.similarity == pytest.approx(chunk.similarity)
        assert citation.snippet == chunk.content.strip()

        # Check source header formatting in context
        expected_header = f"--- [Source {idx}: {chunk.source_filename} (Page {chunk.page_number})] ---"
        assert expected_header in prompt.formatted_context


def test_prompt_builder_empty_chunks_fallback():
    """Verify build_prompt safely outputs fallback context when no chunks are retrieved."""
    builder = PromptBuilder()
    prompt = builder.build_prompt(query="Any unsupported question", retrieved_chunks=[])

    assert prompt.formatted_context == "[NO RELEVANT CONTEXT FOUND]"
    assert len(prompt.citations_map) == 0
    assert prompt.chunk_count == 0


def test_prompt_builder_custom_system_instruction_override():
    """Verify custom system_instruction passed to constructor overrides default asset."""
    custom_instruction = "You are a specialized test assistant. Adhere strictly to provided facts."
    builder = PromptBuilder(system_instruction=custom_instruction)

    assert builder.system_instruction == custom_instruction
    prompt = builder.build_prompt(query="Test query", retrieved_chunks=[])
    assert prompt.system_instruction == custom_instruction
    assert custom_instruction in prompt.full_prompt_text


def test_citation_info_and_augmented_prompt_to_dict(sample_retrieved_chunks):
    """Verify serialization to dictionary representation."""
    builder = PromptBuilder()
    prompt = builder.build_prompt("Test serialization", sample_retrieved_chunks)
    prompt_dict = prompt.to_dict()

    assert "system_instruction" in prompt_dict
    assert "formatted_context" in prompt_dict
    assert "user_query" in prompt_dict
    assert "citations" in prompt_dict
    assert len(prompt_dict["citations"]) == len(sample_retrieved_chunks)

    first_cit = prompt_dict["citations"][0]
    assert first_cit["source_index"] == 1
    assert first_cit["filename"] == "acme_hr_policy.txt"
