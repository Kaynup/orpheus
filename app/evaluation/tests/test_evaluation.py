"""Unit tests for the RAG benchmark evaluation suite."""

import pytest
from app.config import AppConfig
from app.evaluation.evaluator import RAGEvaluator
from app.evaluation.test_dataset import EvaluationTestCase
from app.pipeline.rag_pipeline import RAGPipeline


def test_evaluator_scoring(tmp_path):
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_eval_test")
    cfg.storage.collection_name = "eval_test_col"
    cfg.llm.model = "offline"

    pipeline = RAGPipeline(app_config=cfg)

    # Ingest document
    doc_path = tmp_path / "hr_test.txt"
    doc_path.write_text("Acme core hours are 10:00 AM to 3:00 PM Eastern Time.", encoding="utf-8")
    pipeline.ingest_document(doc_path)

    evaluator = RAGEvaluator(pipeline)

    test_case_supported = EvaluationTestCase(
        test_id="T1",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00", "3:00"],
        expected_source_files=["hr_test.txt"],
        should_refuse=False,
        description="Check core hours",
    )
    res_supported = evaluator.evaluate_test_case(test_case_supported)
    assert res_supported.passed is True
    assert res_supported.retrieval_passed is True

    test_case_unsupported = EvaluationTestCase(
        test_id="T2",
        question="What is the recipe for chocolate cake?",
        category="out_of_scope",
        expected_keywords=["insufficient"],
        expected_source_files=[],
        should_refuse=True,
        description="Check refusal",
    )
    res_unsupported = evaluator.evaluate_test_case(test_case_unsupported)
    assert res_unsupported.refusal_passed is True
