"""Automated evaluation framework for RAG retrieval, grounding, citation accuracy, and hallucination refusal."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.evaluation.test_dataset import BENCHMARK_TEST_SUITE, EvaluationTestCase
from app.logging_config import logger
from app.pipeline.rag_pipeline import QueryResult, RAGPipeline


@dataclass
class TestCaseResult:
    """Detailed outcome of a single evaluation test case."""
    test_id: str
    question: str
    category: str
    passed: bool
    retrieval_passed: bool
    grounding_passed: bool
    citation_passed: bool
    refusal_passed: bool
    is_refusal: bool
    retrieved_sources: List[str]
    cited_sources: List[str]
    answer_preview: str
    latency_ms: float
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "question": self.question,
            "category": self.category,
            "passed": self.passed,
            "retrieval_passed": self.retrieval_passed,
            "grounding_passed": self.grounding_passed,
            "citation_passed": self.citation_passed,
            "refusal_passed": self.refusal_passed,
            "is_refusal": self.is_refusal,
            "retrieved_sources": self.retrieved_sources,
            "cited_sources": self.cited_sources,
            "answer_preview": self.answer_preview,
            "latency_ms": round(self.latency_ms, 2),
            "failure_reasons": self.failure_reasons,
        }


@dataclass
class EvaluationReport:
    """Comprehensive evaluation benchmark report."""
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate_pct: float
    avg_latency_ms: float
    retrieval_accuracy_pct: float
    grounding_accuracy_pct: float
    refusal_accuracy_pct: float
    results: List[TestCaseResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate_pct": round(self.pass_rate_pct, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "retrieval_accuracy_pct": round(self.retrieval_accuracy_pct, 1),
            "grounding_accuracy_pct": round(self.grounding_accuracy_pct, 1),
            "refusal_accuracy_pct": round(self.refusal_accuracy_pct, 1),
            "results": [r.to_dict() for r in self.results],
            "timestamp": self.timestamp,
        }


class RAGEvaluator:
    """
    Evaluates a RAGPipeline against benchmark test cases.
    """

    def __init__(self, pipeline: RAGPipeline):
        self.pipeline = pipeline

    def evaluate_test_case(self, test_case: EvaluationTestCase) -> TestCaseResult:
        """Run a single test case through the pipeline and score results."""
        logger.info("Evaluating test case %s: '%s'...", test_case.test_id, test_case.question)

        start_time = time.perf_counter()
        query_result: QueryResult = self.pipeline.answer_query(test_case.question)
        latency_ms = (time.perf_counter() - start_time) * 1000

        retrieved_sources = list({c.source_filename for c in query_result.retrieved_chunks if c.source_filename})
        cited_sources = list({c.filename for c in query_result.citations if c.filename})
        answer_text = query_result.answer.strip()
        is_refusal = query_result.is_refusal

        failure_reasons: List[str] = []

        # 1. Evaluate Refusal behavior
        if test_case.should_refuse:
            # Must refuse out-of-scope/unsupported questions
            refusal_passed = is_refusal or "insufficient information" in answer_text.lower() or "not have sufficient" in answer_text.lower()
            if not refusal_passed:
                failure_reasons.append("Expected refusal on unsupported question, but model generated ungrounded answer.")
            retrieval_passed = True  # Irrelevant retrieval is expected/permitted for out of scope
            grounding_passed = refusal_passed
            citation_passed = True
        else:
            # Must NOT refuse supported questions
            refusal_passed = not is_refusal
            if not refusal_passed:
                failure_reasons.append("Model erroneously refused supported question.")

            # 2. Evaluate Retrieval correctness
            retrieval_passed = True
            for expected_doc in test_case.expected_source_files:
                if not any(expected_doc.lower() in src.lower() for src in retrieved_sources):
                    retrieval_passed = False
                    failure_reasons.append(f"Expected source '{expected_doc}' not found in retrieved chunks.")

            # 3. Evaluate Grounding (check for key terms in answer)
            matched_keywords = [
                kw for kw in test_case.expected_keywords
                if kw.lower() in answer_text.lower()
            ]
            grounding_passed = len(matched_keywords) >= max(1, len(test_case.expected_keywords) // 2)
            if not grounding_passed:
                failure_reasons.append(
                    f"Answer missing expected factual keywords: {test_case.expected_keywords} (found: {matched_keywords})"
                )

            # 4. Evaluate Citation presence
            has_citation = bool(cited_sources) or "[Source" in answer_text or "[source" in answer_text
            citation_passed = has_citation
            if not citation_passed:
                failure_reasons.append("Answer lacks required source citations.")

        overall_passed = retrieval_passed and grounding_passed and citation_passed and refusal_passed

        logger.info(
            "Test %s (%s): Passed=%s (retrieval=%s, grounding=%s, citation=%s, refusal=%s)",
            test_case.test_id,
            test_case.category,
            overall_passed,
            retrieval_passed,
            grounding_passed,
            citation_passed,
            refusal_passed,
        )

        return TestCaseResult(
            test_id=test_case.test_id,
            question=test_case.question,
            category=test_case.category,
            passed=overall_passed,
            retrieval_passed=retrieval_passed,
            grounding_passed=grounding_passed,
            citation_passed=citation_passed,
            refusal_passed=refusal_passed,
            is_refusal=is_refusal,
            retrieved_sources=retrieved_sources,
            cited_sources=cited_sources,
            answer_preview=answer_text[:200] + ("..." if len(answer_text) > 200 else ""),
            latency_ms=latency_ms,
            failure_reasons=failure_reasons,
        )

    def run_benchmark(
        self,
        test_cases: Optional[List[EvaluationTestCase]] = None,
    ) -> EvaluationReport:
        """Run all test cases in the benchmark suite and compute aggregate metrics."""
        cases = test_cases or BENCHMARK_TEST_SUITE
        logger.info("=== Starting RAG Evaluation Benchmark on %d test cases ===", len(cases))

        results: List[TestCaseResult] = []
        for case in cases:
            res = self.evaluate_test_case(case)
            results.append(res)

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = (passed / total) * 100 if total > 0 else 0.0

        avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0.0
        retrieval_acc = (sum(1 for r in results if r.retrieval_passed) / total) * 100 if total > 0 else 0.0
        grounding_acc = (sum(1 for r in results if r.grounding_passed) / total) * 100 if total > 0 else 0.0
        refusal_acc = (sum(1 for r in results if r.refusal_passed) / total) * 100 if total > 0 else 0.0

        report = EvaluationReport(
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            retrieval_accuracy_pct=retrieval_acc,
            grounding_accuracy_pct=grounding_acc,
            refusal_accuracy_pct=refusal_acc,
            results=results,
        )

        logger.info(
            "=== Evaluation Benchmark Complete: %d/%d passed (%.1f%%) in avg %.1fms ===",
            passed,
            total,
            pass_rate,
            avg_latency,
        )
        return report
