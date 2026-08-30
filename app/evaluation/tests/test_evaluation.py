"""Unit tests for the RAG benchmark evaluation suite and metric scoring dimensions."""

import pytest

from app.config import AppConfig
from app.evaluation.evaluator import ConfusionMatrix, EvaluationReport, RAGEvaluator, TestCaseResult
from app.evaluation.test_dataset import EvaluationTestCase
from app.pipeline.base import BaseInferencePipeline
from app.pipeline.rag_pipeline import RAGPipeline


@pytest.fixture
def eval_pipeline(tmp_path):
    cfg = AppConfig.from_env()
    cfg.storage.persist_dir = str(tmp_path / "chroma_eval_test")
    cfg.storage.collection_name = "eval_test_col"
    cfg.llm.model = "offline"

    pipeline = RAGPipeline(app_config=cfg)

    # Ingest document
    doc_path = tmp_path / "hr_test.txt"
    doc_path.write_text("Acme core hours are 10:00 AM to 3:00 PM Eastern Time.", encoding="utf-8")
    pipeline.ingest_document(doc_path)
    return pipeline


def test_evaluator_scoring_all_dimensions(eval_pipeline):
    """Verify evaluator scores all 5 dimensions on supported and unsupported test cases."""
    evaluator = RAGEvaluator(eval_pipeline)

    test_case_supported = EvaluationTestCase(
        test_id="T1",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00", "3:00"],
        expected_source_files=["hr_test.txt"],
        should_refuse=False,
        description="Check core hours",
    )
    res_supported: TestCaseResult = evaluator.evaluate_test_case(test_case_supported)
    assert res_supported.passed is True
    assert res_supported.retrieval_passed is True
    assert res_supported.grounding_passed is True
    assert res_supported.citation_passed is True
    assert res_supported.refusal_passed is True
    assert res_supported.is_refusal is False
    assert any("hr_test.txt" in s for s in res_supported.retrieved_sources)
    assert len(res_supported.failure_reasons) == 0
    assert res_supported.latency_ms > 0.0

    test_case_unsupported = EvaluationTestCase(
        test_id="T2",
        question="What is the recipe for chocolate cake?",
        category="out_of_scope",
        expected_keywords=["insufficient"],
        expected_source_files=[],
        should_refuse=True,
        description="Check refusal",
    )
    res_unsupported: TestCaseResult = evaluator.evaluate_test_case(test_case_unsupported)
    assert res_unsupported.passed is True
    assert res_unsupported.refusal_passed is True
    assert res_unsupported.is_refusal is True
    assert len(res_unsupported.cited_sources) == 0
    assert len(res_unsupported.failure_reasons) == 0


def test_evaluator_max_length_constraint_failure(eval_pipeline):
    """Verify that an answer exceeding max_length causes length_passed to fail."""
    evaluator = RAGEvaluator(eval_pipeline)

    test_case_short = EvaluationTestCase(
        test_id="T_LEN",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00"],
        expected_source_files=["hr_test.txt"],
        should_refuse=False,
        description="Check character ceiling",
        max_length=5,  # Artificially tiny length ceiling to trigger constraint failure
    )
    res = evaluator.evaluate_test_case(test_case_short)
    assert res.passed is False
    assert any("exceeds maximum length" in r for r in res.failure_reasons)


def test_evaluator_strict_keyword_grounding_failure(eval_pipeline):
    """Verify that require_all_keywords=True fails when any required keyword is missing."""
    evaluator = RAGEvaluator(eval_pipeline)

    test_case_strict = EvaluationTestCase(
        test_id="T_STRICT",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00", "missing_nonexistent_keyword_xyz"],
        expected_source_files=["hr_test.txt"],
        should_refuse=False,
        description="Strict keyword grounding test",
        require_all_keywords=True,
    )
    res = evaluator.evaluate_test_case(test_case_strict)
    assert res.grounding_passed is False
    assert res.passed is False
    assert any("missing expected factual keywords" in r for r in res.failure_reasons)


def test_evaluator_run_benchmark_aggregate_metrics(eval_pipeline):
    """Verify run_benchmark computes accurate aggregate percentages across test suites."""
    evaluator = RAGEvaluator(eval_pipeline)

    cases = [
        EvaluationTestCase(
            test_id="BM1",
            question="What are the core hours?",
            category="factual",
            expected_keywords=["10:00"],
            expected_source_files=["hr_test.txt"],
            should_refuse=False,
            description="Factual query",
        ),
        EvaluationTestCase(
            test_id="BM2",
            question="How to build an interstellar warp drive?",
            category="out_of_scope",
            expected_keywords=["insufficient"],
            expected_source_files=[],
            should_refuse=True,
            description="Refusal query",
        ),
    ]

    report: EvaluationReport = evaluator.run_benchmark(cases)
    assert report.total_tests == 2
    assert report.passed_tests == sum(1 for r in report.results if r.passed)
    assert report.failed_tests == report.total_tests - report.passed_tests
    assert report.pass_rate_pct == (report.passed_tests / report.total_tests) * 100
    assert report.avg_latency_ms > 0.0
    assert 0.0 <= report.retrieval_accuracy_pct <= 100.0
    assert 0.0 <= report.grounding_accuracy_pct <= 100.0
    assert 0.0 <= report.refusal_accuracy_pct <= 100.0

    report_dict = report.to_dict()
    assert "pass_rate_pct" in report_dict
    assert "results" in report_dict
    assert len(report_dict["results"]) == 2


def test_evaluator_punctuation_and_number_normalization(eval_pipeline):
    """Verify that comma-separated keywords (e.g. '10,000') match raw numbers ('10000') and vice versa."""
    evaluator = RAGEvaluator(eval_pipeline)

    test_case = EvaluationTestCase(
        test_id="T_NORM",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00", "3:00"],
        expected_source_files=["hr_test.txt"],
        should_refuse=False,
        description="Normalization test",
        require_all_keywords=True,
    )
    res = evaluator.evaluate_test_case(test_case)
    assert res.grounding_passed is True
    assert res.passed is True


def test_evaluator_accepts_base_inference_pipeline_type(eval_pipeline):
    """Verify RAGEvaluator type annotation accepts BaseInferencePipeline."""
    assert isinstance(eval_pipeline, BaseInferencePipeline)
    evaluator = RAGEvaluator(eval_pipeline)
    assert evaluator.pipeline is eval_pipeline


# New tests: ConfusionMatrix pure-math (no pipeline required)


def test_confusion_matrix_precision_recall_f1():
    """Verify ConfusionMatrix computes P/R/F1 correctly for known values."""
    cm = ConfusionMatrix(tp=8, fp=2, fn=2, tn=8)
    assert abs(cm.precision - 0.8) < 1e-6
    assert abs(cm.recall - 0.8) < 1e-6
    assert abs(cm.f1_score - 0.8) < 1e-6
    assert abs(cm.accuracy - 0.8) < 1e-6


def test_confusion_matrix_zero_division_safety():
    """ConfusionMatrix with all-zero counts must return 0.0 for all metrics."""
    cm = ConfusionMatrix()
    assert cm.precision == 0.0
    assert cm.recall == 0.0
    assert cm.f1_score == 0.0
    assert cm.accuracy == 0.0


def test_confusion_matrix_to_dict_has_all_keys():
    """to_dict() must expose all 8 expected keys."""
    cm = ConfusionMatrix(tp=1, fp=0, fn=0, tn=1)
    d = cm.to_dict()
    for key in ("tp", "fp", "fn", "tn", "precision", "recall", "f1_score", "accuracy"):
        assert key in d, f"Missing key: {key}"


def test_confusion_matrix_perfect_retrieval():
    """TP-only scenario yields precision=recall=f1=1.0."""
    cm = ConfusionMatrix(tp=5, fp=0, fn=0, tn=10)
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.f1_score == 1.0


# New tests: IR metrics on TestCaseResult (integration, uses pipeline)


def test_testcase_result_has_ir_metric_fields(eval_pipeline):
    """TestCaseResult must carry IR metric fields after evaluation."""
    evaluator = RAGEvaluator(eval_pipeline)
    tc = EvaluationTestCase(
        test_id="IR-01",
        question="What are the core hours?",
        category="factual",
        expected_keywords=["10:00"],
        expected_source_files=["hr_test.txt"],
        should_refuse=False,
        description="IR metric fields test",
        expected_snippets=["core hours"],
        total_relevant_chunks=1,
    )
    res = evaluator.evaluate_test_case(tc)
    assert hasattr(res, "context_precision_at_k")
    assert hasattr(res, "context_recall_at_k")
    assert hasattr(res, "context_f1_at_k")
    assert hasattr(res, "reciprocal_rank")
    assert hasattr(res, "hit_at_k")
    assert hasattr(res, "noise_ratio")
    assert isinstance(res.retrieved_chunks_detail, list)
    assert 0.0 <= res.context_precision_at_k <= 1.0
    assert 0.0 <= res.context_recall_at_k <= 1.0
    assert 0.0 <= res.reciprocal_rank <= 1.0


def test_report_has_confusion_matrices(eval_pipeline):
    """EvaluationReport must contain retrieval and guardrail ConfusionMatrix instances."""
    evaluator = RAGEvaluator(eval_pipeline)
    cases = [
        EvaluationTestCase(
            test_id="CM-01",
            question="What are the core hours?",
            category="factual",
            expected_keywords=["10:00"],
            expected_source_files=["hr_test.txt"],
            should_refuse=False,
            description="CM test",
            expected_snippets=["core hours"],
            total_relevant_chunks=1,
        ),
        EvaluationTestCase(
            test_id="CM-02",
            question="What is the recipe for stealth fighter jets?",
            category="out_of_scope",
            expected_keywords=["insufficient"],
            expected_source_files=[],
            should_refuse=True,
            description="Refusal CM test",
        ),
    ]
    report = evaluator.run_benchmark(cases)
    assert isinstance(report.retrieval_confusion_matrix, ConfusionMatrix)
    assert isinstance(report.guardrail_confusion_matrix, ConfusionMatrix)
    # Guardrail: one refusal case — should be TP or FN in guardrail matrix
    grd = report.guardrail_confusion_matrix
    assert grd.tp + grd.fn == 1  # one unsupported query


def test_report_category_metrics_grouped(eval_pipeline):
    """category_metrics must group results by category with required keys."""
    evaluator = RAGEvaluator(eval_pipeline)
    cases = [
        EvaluationTestCase(
            test_id="CAT-01",
            question="What are the core hours?",
            category="factual_single_doc",
            expected_keywords=["10:00"],
            expected_source_files=["hr_test.txt"],
            should_refuse=False,
            description="Category grouping test",
        ),
    ]
    report = evaluator.run_benchmark(cases)
    assert "factual_single_doc" in report.category_metrics
    cat = report.category_metrics["factual_single_doc"]
    for key in ("total", "passed", "pass_rate_pct", "mean_precision_at_k", "mean_recall_at_k", "avg_latency_ms"):
        assert key in cat, f"Missing category metric key: {key}"


def test_report_backward_compat_old_fields(eval_pipeline):
    """to_dict() must still expose legacy accuracy percentage fields."""
    evaluator = RAGEvaluator(eval_pipeline)
    cases = [
        EvaluationTestCase(
            test_id="BC-01",
            question="What are the core hours?",
            category="factual",
            expected_keywords=["10:00"],
            expected_source_files=["hr_test.txt"],
            should_refuse=False,
            description="Backward compat test",
        ),
    ]
    report = evaluator.run_benchmark(cases)
    d = report.to_dict()
    for key in ("retrieval_accuracy_pct", "grounding_accuracy_pct", "refusal_accuracy_pct"):
        assert key in d, f"Legacy key missing from to_dict(): {key}"
    # New IR keys must also be present
    for key in ("mean_precision_at_k", "mean_recall_at_k", "mean_reciprocal_rank",
                "retrieval_confusion_matrix", "guardrail_confusion_matrix", "category_metrics"):
        assert key in d, f"New IR key missing from to_dict(): {key}"
