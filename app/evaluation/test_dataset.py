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


BENCHMARK_TEST_SUITE: List[EvaluationTestCase] = [
    EvaluationTestCase(
        test_id="EVAL-01",
        question="What are the core collaboration hours at Acme Corporation?",
        category="factual_single_doc",
        expected_keywords=["10:00", "3:00", "Eastern", "ET"],
        expected_source_files=["acme_hr_policy.txt"],
        should_refuse=False,
        description="Verify retrieval and extraction of specific work schedule hours.",
    ),
    EvaluationTestCase(
        test_id="EVAL-02",
        question="How much is the home office equipment stipend for remote employees, and what days are in-office?",
        category="factual_single_doc",
        expected_keywords=["750", "Tuesdays", "Thursdays"],
        expected_source_files=["acme_hr_policy.txt"],
        should_refuse=False,
        description="Verify multi-attribute extraction from HR policy.",
    ),
    EvaluationTestCase(
        test_id="EVAL-03",
        question="What is the monthly downtime limit for the 99.99% cloud SLA guarantee?",
        category="factual_single_doc",
        expected_keywords=["4.38", "downtime", "99.99%"],
        expected_source_files=["cloud_architecture_handbook.txt"],
        should_refuse=False,
        description="Verify extraction of numerical reliability SLA bounds.",
    ),
    EvaluationTestCase(
        test_id="EVAL-04",
        question="What are the default Redis caching TTL values for session data and static configuration?",
        category="factual_single_doc",
        expected_keywords=["15", "minute", "24", "hour"],
        expected_source_files=["cloud_architecture_handbook.txt"],
        should_refuse=False,
        description="Verify technical parameter retrieval across list items.",
    ),
    EvaluationTestCase(
        test_id="EVAL-05",
        question="What is the energy conversion efficiency range for monocrystalline solar panels under STC?",
        category="factual_single_doc",
        expected_keywords=["20%", "22.8%"],
        expected_source_files=["renewable_energy_faq.txt"],
        should_refuse=False,
        description="Verify percentage range retrieval from scientific/energy FAQ.",
    ),
    EvaluationTestCase(
        test_id="EVAL-06",
        question="What is the cycle life of LiFePO4 batteries at 80% Depth of Discharge and optimal temperature?",
        category="factual_single_doc",
        expected_keywords=["6,000", "8,000", "15", "35"],
        expected_source_files=["renewable_energy_faq.txt"],
        should_refuse=False,
        description="Verify multi-metric extraction from battery specs.",
    ),
    EvaluationTestCase(
        test_id="EVAL-07",
        question="What embedding model and vector dimension does the Doc-QA Assistant use?",
        category="factual_single_doc",
        expected_keywords=["MiniLM", "384"],
        expected_source_files=["doc_qa_system_manual.txt"],
        should_refuse=False,
        description="Verify system architecture specification retrieval.",
    ),
    EvaluationTestCase(
        test_id="EVAL-08",
        question="What is Acme's policy regarding interstellar space travel reimbursement?",
        category="out_of_scope_refusal",
        expected_keywords=["not have sufficient information", "insufficient"],
        expected_source_files=[],
        should_refuse=True,
        description="Verify hallucination guardrail triggers refusal on completely unsupported topic.",
    ),
    EvaluationTestCase(
        test_id="EVAL-09",
        question="What is the stock price prediction for Acme Corporation for next year?",
        category="out_of_scope_refusal",
        expected_keywords=["not have sufficient information", "insufficient"],
        expected_source_files=[],
        should_refuse=True,
        description="Verify refusal on financial speculation not in context.",
    ),
    EvaluationTestCase(
        test_id="EVAL-10",
        question="What is the circuit breaker trigger condition in cloud architecture and what is parental leave duration in HR policy?",
        category="factual_multi_doc",
        expected_keywords=["50%", "16", "week"],
        expected_source_files=["cloud_architecture_handbook.txt", "acme_hr_policy.txt"],
        should_refuse=False,
        description="Verify multi-document context retrieval across disparate subjects.",
    ),
]
