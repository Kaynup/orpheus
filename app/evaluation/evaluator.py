"""Automated evaluation framework for RAG retrieval, grounding, citation accuracy,
and hallucination refusal — with industry-standard IR metrics and confusion matrices.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.evaluation.test_dataset import BENCHMARK_TEST_SUITE, EvaluationTestCase
from app.logging_config import logger
from app.pipeline.base import BaseInferencePipeline
from app.pipeline.models import QueryResult


@dataclass
class ConfusionMatrix:
    """2×2 confusion-matrix accumulator with derived IR metrics."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.fn + self.tn
        return (self.tp + self.tn) / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.accuracy, 4),
        }


# Per-test Result


@dataclass
class TestCaseResult:
    """Detailed outcome of a single evaluation test case."""

    __test__ = False
    test_id: str
    question: str
    category: str
    passed: bool

    # Legacy boolean dimensions (kept for backward compatibility)
    retrieval_passed: bool
    grounding_passed: bool
    citation_passed: bool
    refusal_passed: bool
    is_refusal: bool

    # Standard IR metrics (v0.2.3+)
    context_precision_at_k: float = 0.0
    context_recall_at_k: float = 0.0
    context_f1_at_k: float = 0.0
    reciprocal_rank: float = 0.0
    hit_at_k: bool = False
    noise_ratio: float = 0.0
    retrieved_chunks_detail: List[Dict[str, Any]] = field(default_factory=list)

    retrieved_sources: List[str] = field(default_factory=list)
    cited_sources: List[str] = field(default_factory=list)
    answer_preview: str = ""
    latency_ms: float = 0.0
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "question": self.question,
            "category": self.category,
            "passed": self.passed,
            # Legacy fields
            "retrieval_passed": self.retrieval_passed,
            "grounding_passed": self.grounding_passed,
            "citation_passed": self.citation_passed,
            "refusal_passed": self.refusal_passed,
            "is_refusal": self.is_refusal,
            # IR metrics
            "context_precision_at_k": round(self.context_precision_at_k, 4),
            "context_recall_at_k": round(self.context_recall_at_k, 4),
            "context_f1_at_k": round(self.context_f1_at_k, 4),
            "reciprocal_rank": round(self.reciprocal_rank, 4),
            "hit_at_k": self.hit_at_k,
            "noise_ratio": round(self.noise_ratio, 4),
            "retrieved_chunks_detail": self.retrieved_chunks_detail,
            # Misc
            "retrieved_sources": self.retrieved_sources,
            "cited_sources": self.cited_sources,
            "answer_preview": self.answer_preview,
            "latency_ms": round(self.latency_ms, 2),
            "failure_reasons": self.failure_reasons,
        }



# Aggregate Report


@dataclass
class EvaluationReport:
    """Comprehensive evaluation benchmark report."""

    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate_pct: float
    avg_latency_ms: float

    # Legacy accuracy percentages (backward-compatible)
    retrieval_accuracy_pct: float
    grounding_accuracy_pct: float
    refusal_accuracy_pct: float

    # Standard IR aggregates (v0.2.3+)
    mean_precision_at_k: float = 0.0
    mean_recall_at_k: float = 0.0
    mean_reciprocal_rank: float = 0.0
    overall_hit_rate_at_k: float = 0.0
    avg_noise_ratio: float = 0.0

    # Dual confusion matrices
    retrieval_confusion_matrix: ConfusionMatrix = field(default_factory=ConfusionMatrix)
    guardrail_confusion_matrix: ConfusionMatrix = field(default_factory=ConfusionMatrix)

    # Per-category breakdown
    category_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)

    results: List[TestCaseResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate_pct": round(self.pass_rate_pct, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            # Legacy
            "retrieval_accuracy_pct": round(self.retrieval_accuracy_pct, 1),
            "grounding_accuracy_pct": round(self.grounding_accuracy_pct, 1),
            "refusal_accuracy_pct": round(self.refusal_accuracy_pct, 1),
            # IR metrics
            "mean_precision_at_k": round(self.mean_precision_at_k, 4),
            "mean_recall_at_k": round(self.mean_recall_at_k, 4),
            "mean_reciprocal_rank": round(self.mean_reciprocal_rank, 4),
            "overall_hit_rate_at_k": round(self.overall_hit_rate_at_k, 4),
            "avg_noise_ratio": round(self.avg_noise_ratio, 4),
            # Confusion matrices
            "retrieval_confusion_matrix": self.retrieval_confusion_matrix.to_dict(),
            "guardrail_confusion_matrix": self.guardrail_confusion_matrix.to_dict(),
            # Category breakdown
            "category_metrics": self.category_metrics,
            "results": [r.to_dict() for r in self.results],
            "timestamp": self.timestamp,
        }



# Evaluator


class RAGEvaluator:
    """Evaluates a pipeline against benchmark test cases.

    Accepts any ``BaseInferencePipeline`` implementation, not just the concrete
    ``RAGPipeline``, enabling independent evaluation runs on the inference sub-pipeline.
    """

    def __init__(self, pipeline: BaseInferencePipeline):
        self.pipeline = pipeline

    # Single test-case evaluation

    def evaluate_test_case(self, test_case: EvaluationTestCase) -> TestCaseResult:
        """Run a single test case through the pipeline and score results."""
        logger.info("Evaluating test case %s: '%s'...", test_case.test_id, test_case.question)

        start_time = time.perf_counter()
        query_result: QueryResult = self.pipeline.answer_query(test_case.question)
        latency_ms = (time.perf_counter() - start_time) * 1000

        retrieved_chunks = query_result.retrieved_chunks
        cited_sources = list({c.filename for c in query_result.citations if c.filename})
        retrieved_sources = list({c.source_filename for c in retrieved_chunks if c.source_filename})
        answer_text = query_result.answer.strip()
        is_refusal = query_result.is_refusal

        failure_reasons: List[str] = []


        # 1. IR metrics — chunk-level relevance scoring

        ir = self._compute_ir_metrics(test_case, retrieved_chunks)


        # 2. Refusal / grounding / citation scoring

        if test_case.should_refuse:
            refusal_passed = (
                is_refusal
                or "insufficient information" in answer_text.lower()
                or "not have sufficient" in answer_text.lower()
            )
            if not refusal_passed:
                failure_reasons.append(
                    "Expected refusal on unsupported question, but model generated ungrounded answer."
                )
            retrieval_passed = True
            grounding_passed = refusal_passed
            citation_passed = True
        else:
            refusal_passed = not is_refusal
            if not refusal_passed:
                failure_reasons.append("Model erroneously refused supported question.")

            retrieval_passed = True
            for expected_doc in test_case.expected_source_files:
                if not any(expected_doc.lower() in src.lower() for src in retrieved_sources):
                    retrieval_passed = False
                    failure_reasons.append(
                        f"Expected source '{expected_doc}' not found in retrieved chunks."
                    )

            def _normalize_text(text: str) -> str:
                return re.sub(r"[\s\-_,]+", " ", text.lower()).strip()

            matched_keywords = []
            answer_lower = answer_text.lower()
            answer_norm = _normalize_text(answer_text)

            for kw in test_case.expected_keywords:
                kw_lower = kw.lower()
                kw_norm = _normalize_text(kw)
                if (kw_lower in answer_lower) or (kw_norm and kw_norm in answer_norm):
                    matched_keywords.append(kw)

            if test_case.require_all_keywords:
                grounding_passed = len(matched_keywords) == len(test_case.expected_keywords)
            else:
                grounding_passed = len(matched_keywords) >= max(1, len(test_case.expected_keywords) // 2)

            if not grounding_passed:
                failure_reasons.append(
                    f"Answer missing expected factual keywords: {test_case.expected_keywords} "
                    f"(found: {matched_keywords})"
                )

            has_citation = bool(cited_sources) or "[Source" in answer_text or "[source" in answer_text
            citation_passed = has_citation
            if not citation_passed:
                failure_reasons.append("Answer lacks required source citations.")


        # 3. Length constraint

        length_passed = True
        if test_case.max_length:
            clean_answer = re.sub(r"\[Source[^\]]*\]", "", answer_text).strip()
            effective_len = min(len(answer_text), len(clean_answer))
            if effective_len > test_case.max_length:
                length_passed = False
                failure_reasons.append(
                    f"Answer exceeds maximum length ({effective_len} > {test_case.max_length} chars)."
                )

        overall_passed = (
            retrieval_passed
            and grounding_passed
            and citation_passed
            and refusal_passed
            and length_passed
        )

        logger.info(
            "Test %s (%s): Passed=%s | P@K=%.2f R@K=%.2f RR=%.2f",
            test_case.test_id,
            test_case.category,
            overall_passed,
            ir["precision_at_k"],
            ir["recall_at_k"],
            ir["reciprocal_rank"],
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
            context_precision_at_k=ir["precision_at_k"],
            context_recall_at_k=ir["recall_at_k"],
            context_f1_at_k=ir["f1_at_k"],
            reciprocal_rank=ir["reciprocal_rank"],
            hit_at_k=ir["hit_at_k"],
            noise_ratio=ir["noise_ratio"],
            retrieved_chunks_detail=ir["chunks_detail"],
            retrieved_sources=retrieved_sources,
            cited_sources=cited_sources,
            answer_preview=answer_text[:200] + ("..." if len(answer_text) > 200 else ""),
            latency_ms=latency_ms,
            failure_reasons=failure_reasons,
        )

    # Benchmark aggregation


    def run_benchmark(
        self,
        test_cases: Optional[List[EvaluationTestCase]] = None,
    ) -> EvaluationReport:
        """Run all test cases and compute aggregate IR metrics plus confusion matrices."""
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

        # Legacy accuracy percentages
        retrieval_acc = (sum(1 for r in results if r.retrieval_passed) / total) * 100 if total > 0 else 0.0
        grounding_acc = (sum(1 for r in results if r.grounding_passed) / total) * 100 if total > 0 else 0.0
        refusal_acc = (sum(1 for r in results if r.refusal_passed) / total) * 100 if total > 0 else 0.0

        # Aggregate IR metrics (exclude refusal cases from retrieval metrics)
        retrieval_cases = [r for r in results if not r.is_refusal]
        n_ret = len(retrieval_cases) or 1

        mean_p = sum(r.context_precision_at_k for r in retrieval_cases) / n_ret
        mean_r = sum(r.context_recall_at_k for r in retrieval_cases) / n_ret
        mrr = sum(r.reciprocal_rank for r in retrieval_cases) / n_ret
        hit_rate = sum(1 for r in retrieval_cases if r.hit_at_k) / n_ret
        noise = sum(r.noise_ratio for r in retrieval_cases) / n_ret

        # Build dual confusion matrices
        ret_cm, grd_cm = self._build_confusion_matrices(results, cases)

        # Per-category breakdown
        category_metrics = self._build_category_metrics(results)

        report = EvaluationReport(
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            retrieval_accuracy_pct=retrieval_acc,
            grounding_accuracy_pct=grounding_acc,
            refusal_accuracy_pct=refusal_acc,
            mean_precision_at_k=mean_p,
            mean_recall_at_k=mean_r,
            mean_reciprocal_rank=mrr,
            overall_hit_rate_at_k=hit_rate,
            avg_noise_ratio=noise,
            retrieval_confusion_matrix=ret_cm,
            guardrail_confusion_matrix=grd_cm,
            category_metrics=category_metrics,
            results=results,
        )

        logger.info(
            "=== Benchmark Complete: %d/%d passed (%.1f%%) | MRR=%.3f P@K=%.3f R@K=%.3f ===",
            passed,
            total,
            pass_rate,
            mrr,
            mean_p,
            mean_r,
        )
        return report

    # Internal helpers

    @staticmethod
    def _compute_ir_metrics(
        test_case: EvaluationTestCase,
        retrieved_chunks: list,
    ) -> Dict[str, Any]:
        """Compute chunk-level P@K, R@K, RR, Hit@K, Noise@K for one test case."""
        k = len(retrieved_chunks)
        if k == 0 or test_case.should_refuse:
            return {
                "precision_at_k": 0.0,
                "recall_at_k": 0.0,
                "f1_at_k": 0.0,
                "reciprocal_rank": 0.0,
                "hit_at_k": False,
                "noise_ratio": 0.0,
                "chunks_detail": [],
            }

        chunks_detail: List[Dict[str, Any]] = []
        tp = 0
        first_relevant_rank: Optional[int] = None

        for rank, chunk in enumerate(retrieved_chunks, start=1):
            source = getattr(chunk, "source_filename", "") or ""
            text = getattr(chunk, "content", "") or ""
            score = getattr(chunk, "similarity", 0.0)

            # Relevance: source file match OR snippet substring match
            source_match = any(
                exp.lower() in source.lower() for exp in test_case.expected_source_files
            )
            snippet_match = any(snip.lower() in text.lower() for snip in test_case.expected_snippets)
            is_relevant = source_match or snippet_match

            if is_relevant:
                tp += 1
                if first_relevant_rank is None:
                    first_relevant_rank = rank

            chunks_detail.append(
                {
                    "rank": rank,
                    "source": source,
                    "score": round(score, 4),
                    "is_relevant": is_relevant,
                    "snippet": text[:120] + ("..." if len(text) > 120 else ""),
                }
            )

        fp = k - tp
        total_relevant = max(test_case.total_relevant_chunks, 1)
        fn = max(0, total_relevant - tp)
        precision = tp / k
        recall = tp / total_relevant
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        rr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
        noise = fp / k

        return {
            "precision_at_k": precision,
            "recall_at_k": recall,
            "f1_at_k": f1,
            "reciprocal_rank": rr,
            "hit_at_k": tp > 0,
            "noise_ratio": noise,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "chunks_detail": chunks_detail,
        }

    @staticmethod
    def _build_confusion_matrices(
        results: List[TestCaseResult],
        cases: List[EvaluationTestCase],
    ) -> tuple[ConfusionMatrix, ConfusionMatrix]:
        """Derive retrieval and guardrail confusion matrices from per-case results."""
        ret_cm = ConfusionMatrix()
        grd_cm = ConfusionMatrix()

        for res, case in zip(results, cases):
            # --- Retrieval matrix (chunk-level, only for non-refusal cases) ---
            if not case.should_refuse and res.retrieved_chunks_detail:
                k = len(res.retrieved_chunks_detail)
                tp_ret = sum(1 for c in res.retrieved_chunks_detail if c["is_relevant"])
                fp_ret = k - tp_ret
                fn_ret = max(0, case.total_relevant_chunks - tp_ret)
                # Estimate TN as corpus chunks not retrieved (approximate with a small constant)
                tn_ret = max(0, 10 - k)
                ret_cm.tp += tp_ret
                ret_cm.fp += fp_ret
                ret_cm.fn += fn_ret
                ret_cm.tn += tn_ret

            # --- Guardrail matrix ---
            if case.should_refuse:
                if res.is_refusal:
                    grd_cm.tp += 1   # Correct refusal
                else:
                    grd_cm.fn += 1   # Hallucination breach
            else:
                if res.is_refusal:
                    grd_cm.fp += 1   # False rejection
                else:
                    grd_cm.tn += 1   # Correct grounded answer

        return ret_cm, grd_cm

    @staticmethod
    def _build_category_metrics(results: List[TestCaseResult]) -> Dict[str, Dict[str, float]]:
        """Group mean IR metrics per category."""
        from collections import defaultdict

        cat_buckets: Dict[str, List[TestCaseResult]] = defaultdict(list)
        for r in results:
            cat_buckets[r.category].append(r)

        category_metrics: Dict[str, Dict[str, float]] = {}
        for cat, bucket in cat_buckets.items():
            n = len(bucket)
            category_metrics[cat] = {
                "total": n,
                "passed": sum(1 for r in bucket if r.passed),
                "pass_rate_pct": round(sum(1 for r in bucket if r.passed) / n * 100, 1),
                "mean_precision_at_k": round(sum(r.context_precision_at_k for r in bucket) / n, 4),
                "mean_recall_at_k": round(sum(r.context_recall_at_k for r in bucket) / n, 4),
                "mean_reciprocal_rank": round(sum(r.reciprocal_rank for r in bucket) / n, 4),
                "avg_latency_ms": round(sum(r.latency_ms for r in bucket) / n, 1),
            }
        return category_metrics
