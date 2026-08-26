"""End-to-end integration tests for RAG pipeline, event streaming,
multi-document lifecycle, and anti-hallucination guardrails.
"""

import pytest

from app.config import AppConfig
from app.pipeline.events import EventStage
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
    """Verify end-to-end QA execution with exact factual recall and citation provenance."""
    result = populated_pipeline.answer_query("How many days of paid vacation do employees receive?")
    assert result.has_relevant_context is True
    assert result.is_refusal is False
    assert len(result.retrieved_chunks) > 0
    assert len(result.citations) > 0

    # Strict factual extraction verification (no loose OR checks)
    assert "20 days" in result.answer

    # Citation provenance verification
    top_citation = result.citations[0]
    assert top_citation.filename == "vacation_policy.txt"
    assert top_citation.source_index == 1
    assert result.prompt.chunk_count == len(result.retrieved_chunks)
    assert result.duration_ms > 0.0


def test_pipeline_unsupported_query_guardrail(populated_pipeline):
    """Verify anti-hallucination guardrail strictly triggers refusal on out-of-scope queries."""
    result = populated_pipeline.answer_query("What is the policy for traveling to Alpha Centauri?")
    assert result.is_refusal is True
    assert len(result.citations) == 0
    assert (
        "not have sufficient information" in result.answer.lower() or "sufficient information" in result.answer.lower()
    )


def test_pipeline_event_streaming_callback(tmp_path):
    """Verify all pipeline stage transitions emit sequential, typed PipelineEvent objects via callback."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_events_test")
    cfg.storage.collection_name = "test_events_col"
    cfg.llm.model = "offline"

    pipeline = RAGPipeline(app_config=cfg)

    ingest_events = []
    sample_file = tmp_path / "events_policy.txt"
    sample_file.write_text("Standard core hours are 10:00 AM to 3:00 PM Eastern Time.", encoding="utf-8")

    # Ingestion events
    pipeline.ingest_document(sample_file, event_callback=ingest_events.append)
    assert len(ingest_events) > 0

    ingest_stages = [e.stage for e in ingest_events]
    assert EventStage.DOC_RECEIVED in ingest_stages
    assert EventStage.TEXT_EXTRACTED in ingest_stages
    assert EventStage.CHUNKS_CREATED in ingest_stages
    assert EventStage.EMBEDDINGS_GENERATED in ingest_stages
    assert EventStage.VECTORS_STORED in ingest_stages
    assert EventStage.INDEXING_COMPLETE in ingest_stages

    # Query events
    query_events = []
    res = pipeline.answer_query("What are the core hours?", event_callback=query_events.append)
    assert res.has_relevant_context is True
    assert len(query_events) > 0

    query_stages = [e.stage for e in query_events]
    assert EventStage.QUERY_RECEIVED in query_stages
    assert EventStage.QUERY_EMBEDDED in query_stages
    assert EventStage.RETRIEVING_CHUNKS in query_stages
    assert EventStage.CONTEXT_SELECTED in query_stages
    assert EventStage.PROMPT_PREPARED in query_stages
    assert EventStage.GENERATING_ANSWER in query_stages
    assert EventStage.ANSWER_COMPLETE in query_stages


def test_pipeline_multi_document_lifecycle_and_deletion(tmp_path):
    """Verify multi-document ingestion, cross-synthesis, and refusal after document deletion."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_lifecycle_test")
    cfg.storage.collection_name = "test_lifecycle_col"
    cfg.llm.model = "offline"

    pipeline = RAGPipeline(app_config=cfg)

    # Ingest Doc A (HR)
    doc_a = tmp_path / "hr_doc.txt"
    doc_a.write_text("Parental leave policy provides 16 weeks of fully paid leave.", encoding="utf-8")
    res_a = pipeline.ingest_document(doc_a)

    # Ingest Doc B (Cloud)
    doc_b = tmp_path / "cloud_doc.txt"
    doc_b.write_text("High availability cloud guarantee allows 4.38 minutes of monthly downtime.", encoding="utf-8")
    pipeline.ingest_document(doc_b)

    # Query Doc A
    q_a = pipeline.answer_query("How many weeks of parental leave are provided?")
    assert q_a.has_relevant_context is True
    assert "16 weeks" in q_a.answer
    assert q_a.citations[0].filename == "hr_doc.txt"

    # Query Doc B
    q_b = pipeline.answer_query("What is the monthly downtime limit?")
    assert q_b.has_relevant_context is True
    assert "4.38" in q_b.answer
    assert q_b.citations[0].filename == "cloud_doc.txt"

    # Delete Doc A
    pipeline.vector_store.delete_document(res_a.doc_id)

    # Query Doc A again -> Must now refuse due to deleted context
    q_a_after = pipeline.answer_query("How many weeks of parental leave are provided?")
    assert q_a_after.is_refusal is True
    assert len(q_a_after.citations) == 0
    assert "16 weeks" not in q_a_after.answer

    # Query Doc B again -> Must still succeed
    q_b_after = pipeline.answer_query("What is the monthly downtime limit?")
    assert q_b_after.has_relevant_context is True
    assert "4.38" in q_b_after.answer
