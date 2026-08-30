"""Standardized 8-10 test cases for RAG pipeline evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EvaluationTestCase:
    """Represents a benchmark test case for RAG verification."""

    test_id: str
    question: str
    category: str  # 'factual_single_doc', 'factual_multi_doc', 'out_of_scope_refusal', 'technical_param'
    expected_keywords: List[str]
    expected_source_files: List[str]
    should_refuse: bool
    description: str
    max_length: Optional[int] = None
    require_all_keywords: bool = False
    # IR metric ground truth
    expected_snippets: List[str] = field(default_factory=list)
    """Factual text substrings that a retrieved chunk must contain to be considered relevant."""
    total_relevant_chunks: int = 1
    """Denominator for Recall@K — number of ground-truth relevant chunks that exist in the corpus."""


BENCHMARK_TEST_SUITE: List[EvaluationTestCase] = [
    EvaluationTestCase(
        test_id="EVAL-01",
        question="What are the core collaboration hours at Acme Corporation? Answer concisely in under 200 characters.",
        category="factual_single_doc",
        expected_keywords=["10:00", "3:00"],
        expected_source_files=["acme_hr_policy.txt"],
        should_refuse=False,
        description="Verify retrieval and extraction of specific work schedule hours with realistic character limits.",
        max_length=250,
        require_all_keywords=True,
        expected_snippets=["10:00 AM", "3:00 PM", "core collaboration hours"],
        total_relevant_chunks=2,
    ),
    EvaluationTestCase(
        test_id="EVAL-02",
        question=(
            "Provide a strict bulleted list stating the home office equipment "
            "stipend for remote employees and the exact days required in-office."
        ),
        category="factual_single_doc",
        expected_keywords=["750", "Tuesdays", "Thursdays"],
        expected_source_files=["acme_hr_policy.txt"],
        should_refuse=False,
        description="Verify multi-attribute extraction and constraint formatting.",
        require_all_keywords=True,
        expected_snippets=["$750", "Tuesdays", "Thursdays", "home office"],
        total_relevant_chunks=2,
    ),
    EvaluationTestCase(
        test_id="EVAL-03",
        question=(
            "What is the monthly downtime limit for the 99.99% cloud SLA guarantee? "
            "Output only the numerical value and unit."
        ),
        category="factual_single_doc",
        expected_keywords=["4.38", "minute"],
        expected_source_files=["cloud_architecture_handbook.txt"],
        should_refuse=False,
        description="Verify extraction of numerical reliability SLA bounds.",
        max_length=150,
        require_all_keywords=True,
        expected_snippets=["4.38 minutes", "99.99%", "monthly downtime"],
        total_relevant_chunks=1,
    ),
    EvaluationTestCase(
        test_id="EVAL-04",
        question="List the default Redis caching TTL values for session data and static configuration.",
        category="factual_single_doc",
        expected_keywords=["15", "minute", "24", "hour"],
        expected_source_files=["cloud_architecture_handbook.txt"],
        should_refuse=False,
        description="Verify technical parameter retrieval across list items.",
        require_all_keywords=True,
        expected_snippets=["15 minutes", "24 hours", "Redis", "session", "static"],
        total_relevant_chunks=2,
    ),
    EvaluationTestCase(
        test_id="EVAL-05",
        question="State the exact energy conversion efficiency range for monocrystalline solar panels under STC.",
        category="factual_single_doc",
        expected_keywords=["20%", "22.8%"],
        expected_source_files=["renewable_energy_faq.txt"],
        should_refuse=False,
        description="Verify percentage range retrieval from scientific/energy FAQ.",
        require_all_keywords=True,
        expected_snippets=["20%", "22.8%", "monocrystalline", "STC"],
        total_relevant_chunks=1,
    ),
    EvaluationTestCase(
        test_id="EVAL-06",
        question="Provide the cycle life of LiFePO4 batteries at 80% Depth of Discharge and optimal temperature.",
        category="factual_single_doc",
        expected_keywords=["6,000", "8,000"],
        expected_source_files=["renewable_energy_faq.txt"],
        should_refuse=False,
        description="Verify multi-metric extraction from battery specs with flexible punctuation normalization.",
        require_all_keywords=True,
        expected_snippets=["6,000", "8,000", "LiFePO4", "Depth of Discharge"],
        total_relevant_chunks=2,
    ),
    EvaluationTestCase(
        test_id="EVAL-07",
        question="Identify the embedding model and vector dimension used by Orpheus in exactly one sentence.",
        category="factual_single_doc",
        expected_keywords=["MiniLM", "384"],
        expected_source_files=["doc_qa_system_manual.txt"],
        should_refuse=False,
        description="Verify system architecture specification retrieval with brevity constraint.",
        max_length=250,
        require_all_keywords=True,
        expected_snippets=["MiniLM", "384", "embedding"],
        total_relevant_chunks=1,
    ),
    EvaluationTestCase(
        test_id="EVAL-08",
        question="What is Acme's policy regarding interstellar space travel reimbursement?",
        category="out_of_scope_refusal",
        expected_keywords=["not have sufficient information", "insufficient"],
        expected_source_files=[],
        should_refuse=True,
        description="Verify hallucination guardrail triggers refusal on completely unsupported topic.",
        expected_snippets=[],
        total_relevant_chunks=0,
    ),
    EvaluationTestCase(
        test_id="EVAL-09",
        question="What is the stock price prediction for Acme Corporation for next year?",
        category="out_of_scope_refusal",
        expected_keywords=["not have sufficient information", "insufficient"],
        expected_source_files=[],
        should_refuse=True,
        description="Verify refusal on financial speculation not in context.",
        expected_snippets=[],
        total_relevant_chunks=0,
    ),
    EvaluationTestCase(
        test_id="EVAL-10",
        question=(
            "Synthesize the circuit breaker trigger condition in cloud architecture "
            "and the parental leave duration in HR policy into a single response."
        ),
        category="factual_multi_doc",
        expected_keywords=["50%", "16", "week"],
        expected_source_files=["cloud_architecture_handbook.txt", "acme_hr_policy.txt"],
        should_refuse=False,
        description="Verify multi-document context retrieval across disparate subjects.",
        require_all_keywords=True,
        expected_snippets=["circuit breaker", "50%", "16 weeks", "parental leave"],
        total_relevant_chunks=3,
    ),
]
