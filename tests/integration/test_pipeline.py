"""End-to-end integration tests for RAG pipeline, event streaming,
multi-document lifecycle, and anti-hallucination guardrails.
"""

import pytest

from app.config import AppConfig
from app.pipeline.base import BaseInferencePipeline, BaseIngestionPipeline, BaseRAGPipeline
from app.pipeline.events import EventStage
from app.pipeline.factory import create_inference_pipeline, create_ingestion_pipeline, create_rag_pipeline
from app.pipeline.inference_pipeline import QueryInferencePipeline
from app.pipeline.ingestion_pipeline import DocumentIngestionPipeline
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


# New tests: pipeline modularity and interface compliance


def test_rag_pipeline_isinstance_checks(tmp_path):
    """Verify RAGPipeline satisfies all base interface protocols."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_isinstance_test")
    cfg.storage.collection_name = "test_isinstance_col"
    pipeline = RAGPipeline(app_config=cfg)
    assert isinstance(pipeline, BaseRAGPipeline)
    assert isinstance(pipeline, BaseIngestionPipeline)
    assert isinstance(pipeline, BaseInferencePipeline)


def test_document_ingestion_pipeline_isolated(tmp_path):
    """Verify DocumentIngestionPipeline operates independently without inference components."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_ingest_isolated")
    cfg.storage.collection_name = "test_ingest_isolated"
    cfg.llm.model = "offline"

    ingestion = DocumentIngestionPipeline(app_config=cfg)
    assert isinstance(ingestion, BaseIngestionPipeline)

    sample_file = tmp_path / "isolated_ingest_doc.txt"
    sample_file.write_text(
        "Isolated ingestion test content for pipeline decoupling verification.",
        encoding="utf-8",
    )
    result = ingestion.ingest_document(sample_file)
    assert result.chunk_count > 0
    assert result.filename == "isolated_ingest_doc.txt"


def test_query_inference_pipeline_isolated(tmp_path):
    """Verify QueryInferencePipeline operates independently using a pre-populated VectorStore."""
    from app.storage.vector_store import VectorStore

    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_infer_isolated")
    cfg.storage.collection_name = "test_infer_isolated"
    cfg.llm.model = "offline"

    shared_store = VectorStore(
        persist_dir=cfg.storage.persist_dir,
        collection_name=cfg.storage.collection_name,
    )
    ingestion = DocumentIngestionPipeline(app_config=cfg, vector_store=shared_store)
    doc_file = tmp_path / "inference_test.txt"
    doc_file.write_text("Acme employees receive 20 days of paid vacation.", encoding="utf-8")
    ingestion.ingest_document(doc_file)

    inference = QueryInferencePipeline(app_config=cfg, vector_store=shared_store)
    assert isinstance(inference, BaseInferencePipeline)

    result = inference.answer_query("How many days of vacation do employees get?")
    assert result.has_relevant_context is True
    assert result.is_refusal is False
    assert "20 days" in result.answer


def test_factory_create_rag_pipeline(tmp_path):
    """Verify create_rag_pipeline factory returns a valid BaseRAGPipeline."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_factory_test")
    cfg.storage.collection_name = "test_factory_col"
    pipeline = create_rag_pipeline(app_config=cfg)
    assert isinstance(pipeline, BaseRAGPipeline)
    assert isinstance(pipeline, RAGPipeline)


def test_factory_create_ingestion_pipeline(tmp_path):
    """Verify create_ingestion_pipeline factory returns a valid BaseIngestionPipeline."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_factory_ingest")
    cfg.storage.collection_name = "test_factory_ingest"
    pipeline = create_ingestion_pipeline(app_config=cfg)
    assert isinstance(pipeline, BaseIngestionPipeline)
    assert isinstance(pipeline, DocumentIngestionPipeline)


def test_factory_create_inference_pipeline(tmp_path):
    """Verify create_inference_pipeline factory returns a valid BaseInferencePipeline."""
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_factory_infer")
    cfg.storage.collection_name = "test_factory_infer"
    pipeline = create_inference_pipeline(app_config=cfg)
    assert isinstance(pipeline, BaseInferencePipeline)
    assert isinstance(pipeline, QueryInferencePipeline)


def test_evaluator_accepts_base_inference_pipeline(tmp_path):
    """Verify RAGEvaluator accepts BaseInferencePipeline — not just concrete RAGPipeline."""
    from app.evaluation.evaluator import RAGEvaluator
    from app.evaluation.test_dataset import EvaluationTestCase
    from app.storage.vector_store import VectorStore

    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_eval_base")
    cfg.storage.collection_name = "test_eval_base"
    cfg.llm.model = "offline"

    shared_store = VectorStore(
        persist_dir=cfg.storage.persist_dir,
        collection_name=cfg.storage.collection_name,
    )
    ingestion = DocumentIngestionPipeline(app_config=cfg, vector_store=shared_store)
    doc_file = tmp_path / "eval_isolation.txt"
    doc_file.write_text(
        "Acme core hours are 10:00 AM to 3:00 PM Eastern Time.",
        encoding="utf-8",
    )
    ingestion.ingest_document(doc_file)

    inference = create_inference_pipeline(app_config=cfg, vector_store=shared_store)
    evaluator = RAGEvaluator(inference)

    case = EvaluationTestCase(
        test_id="BASE-01",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00", "3:00"],
        expected_source_files=["eval_isolation.txt"],
        should_refuse=False,
        description="Verify evaluator works with raw BaseInferencePipeline",
    )
    result = evaluator.evaluate_test_case(case)
    assert result.retrieval_passed is True
