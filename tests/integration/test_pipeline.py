"""End-to-end unit tests for RAG pipeline and anti-hallucination guardrail."""

import pytest
from app.config import AppConfig
from app.pipeline.rag_pipeline import RAGPipeline


@pytest.fixture
def populated_pipeline(tmp_path):
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_pipeline_test")
    cfg.storage.collection_name = "test_pipeline_collection"
    cfg.llm.model = "offline"

    pipeline = RAGPipeline(app_config=cfg)

    # Ingest a sample doc
    sample_file = tmp_path / "vacation_policy.txt"
    sample_file.write_text(
        "Acme employees get 20 days of paid vacation annually. Parental leave is 16 weeks fully paid.",
        encoding="utf-8",
    )
    pipeline.ingest_document(sample_file)
    return pipeline


def test_pipeline_supported_query(populated_pipeline):
    result = populated_pipeline.answer_query("How many days of paid vacation do employees receive?")
    assert result.has_relevant_context is True
    assert result.is_refusal is False
    assert len(result.retrieved_chunks) > 0
    assert len(result.citations) > 0
    assert "20 days" in result.answer or "vacation" in result.answer


def test_pipeline_unsupported_query_guardrail(populated_pipeline):
    result = populated_pipeline.answer_query("What is the policy for traveling to Alpha Centauri?")
    # Must refuse or indicate insufficient information
    assert result.is_refusal is True or "not have sufficient information" in result.answer.lower()
