# How Evaluation and Scoring Work in Doc-QA Assistant

This document explains in detail how the automated benchmark evaluation engine works in [`app/evaluation/evaluator.py`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/evaluator.py) and [`app/evaluation/test_dataset.py`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/test_dataset.py), how individual test cases are scored across multiple dimensions, and how aggregate metrics are calculated.

---

## 1. Overview of the Evaluation Architecture

The benchmark evaluates the entire RAG pipeline as a cohesive unit. Rather than simply checking if an LLM produced *some* response, it objectively tests whether the pipeline:
1. **Retrieved the right source documents** (Retrieval Accuracy).
2. **Extracted and answered with factual truth** (Grounding Faithfulness).
3. **Cited its sources properly** (Citation Presence).
4. **Refused unanswerable or out-of-scope questions** (Anti-Hallucination Refusal).

```
                 [EvaluationTestCase]
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
[Pipeline Execution]             [Expected Ground Truth]
 • Retrieved Chunks               • Expected Source Files
 • Generated Answer               • Expected Factual Keywords
 • Citations List                 • should_refuse Flag
 • Refusal Status
            │                           │
            └─────────────┬─────────────┘
                          ▼
            [4-Pillar Scoring Engine]
   1. Refusal Check     ──► refusal_passed (True/False)
   2. Retrieval Check   ──► retrieval_passed (True/False)
   3. Grounding Check   ──► grounding_passed (True/False)
   4. Citation Check    ──► citation_passed (True/False)
                          │
                          ▼
         overall_passed = (1 ∧ 2 ∧ 3 ∧ 4)
```

---

## 2. Test Case Schema (`EvaluationTestCase`)

Each benchmark test case in [`app/evaluation/test_dataset.py`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/test_dataset.py) is defined with clear expectations:

```python
@dataclass
class EvaluationTestCase:
    test_id: str                      # Unique ID (e.g. "EVAL-01")
    question: str                     # The exact test query
    category: str                     # "factual_single_doc", "factual_multi_doc", "out_of_scope_refusal"
    expected_keywords: List[str]      # Key factual strings that must appear in the answer
    expected_source_files: List[str]  # Documents that must be in the top retrieved chunks
    should_refuse: bool               # True if this query must trigger anti-hallucination refusal
    description: str                  # Educational explanation of what is tested
```

---

## 3. The 4 Scoring Pillars

For every query passed through `RAGEvaluator.evaluate_test_case(test_case)`, the evaluator checks four criteria:

### Pillar 1: Anti-Hallucination Refusal (`refusal_passed`)

This verifies whether the pipeline correctly identifies what it does *not* know:

* **When `should_refuse == True` (Out-of-scope query, e.g. Space Policy, Stock Predictions)**:
  * The response passes if `is_refusal == True` **OR** contains standard refusal phrases:
    * `"insufficient information"`
    * `"not have sufficient"`
  * If the model attempts to invent an answer, `refusal_passed = False`, and a failure reason is logged:
    `"Expected refusal on unsupported question, but model generated ungrounded answer."`
* **When `should_refuse == False` (Supported factual query)**:
  * The response passes if `is_refusal == False`.
  * If the model erroneously refused to answer a valid question, `refusal_passed = False`.

---

### Pillar 2: Retrieval Accuracy (`retrieval_passed`)

This verifies whether the semantic retriever found the correct documents in the top-$k$ results:

* For supported queries (`should_refuse == False`), the evaluator checks the list of retrieved source filenames (`retrieved_sources`):
  ```python
  retrieval_passed = True
  for expected_doc in test_case.expected_source_files:
      if not any(expected_doc.lower() in src.lower() for src in retrieved_sources):
          retrieval_passed = False
          failure_reasons.append(f"Expected source '{expected_doc}' not found in retrieved chunks.")
  ```
* For out-of-scope queries (`should_refuse == True`), retrieval is automatically marked `True` because whatever low-similarity chunks were returned are irrelevant.

---

### Pillar 3: Grounding Faithfulness (`grounding_passed`)

This verifies whether the answer contains the necessary factual keywords:

* The evaluator matches `expected_keywords` against the lowercase answer text:
  ```python
  matched_keywords = [
      kw for kw in test_case.expected_keywords
      if kw.lower() in answer_text.lower()
  ]
  # Requires at least half (or at least 1) of the expected keywords
  grounding_passed = len(matched_keywords) >= max(1, len(test_case.expected_keywords) // 2)
  ```
* **Example**:
  * For the question *"What are the core collaboration hours?"*:
  * Expected keywords: `["10:00", "3:00", "eastern"]`
  * If the answer contains `"10:00 AM to 3:00 PM Eastern Time"`, all 3 match $\rightarrow$ **PASS**.

---

### Pillar 4: Citation Validity (`citation_passed`)

This verifies that the response credits its source:

* For supported questions, the evaluator verifies that at least one of the following is true:
  1. `cited_sources` list is non-empty.
  2. The answer string contains a citation marker (`[Source N]` or `[Source N: filename]`).
* If citations are missing on factual answers, `citation_passed = False`.

---

## 4. Overall Test Case Pass / Fail Calculation

A test case passes if and only if **all four pillars pass**:

$$\text{overall\_passed} = \text{retrieval\_passed} \land \text{grounding\_passed} \land \text{citation\_passed} \land \text{refusal\_passed}$$

If any pillar fails, `overall_passed = False`, and the specific failure reasons are recorded in `failure_reasons`.

---

## 5. Aggregate Benchmark Metrics & Formulas

When the full benchmark runs (`RAGEvaluator.run_benchmark()`), aggregate metrics are calculated across all test cases ($N$):

| Metric | Mathematical Formula | Description |
| :--- | :--- | :--- |
| **Overall Pass Rate** | $\frac{\sum \text{passed}}{N} \times 100\%$ | Percentage of test cases where all 4 pillars passed. |
| **Retrieval Accuracy** | $\frac{\sum \text{retrieval\_passed}}{N} \times 100\%$ | Percentage of queries where the correct source document was in top-$k$. |
| **Grounding Accuracy** | $\frac{\sum \text{grounding\_passed}}{N} \times 100\%$ | Percentage of queries where factual keywords were present. |
| **Refusal Accuracy** | $\frac{\sum \text{refusal\_passed}}{N} \times 100\%$ | Percentage of queries where guardrail refusals triggered correctly. |
| **Average Latency** | $\frac{\sum \text{latency\_ms}}{N}$ | Mean end-to-end response time in milliseconds. |

---

## 6. Concrete Scoring Examples

### Example A: Supported Single-Document Query (`EVAL-01`)
* **Question**: *"What are the core collaboration hours at Acme Corporation?"*
* **Pipeline Output**: *"Core collaboration hours are 10:00 AM to 3:00 PM Eastern Time (ET), Monday through Friday. [Source 1: acme_hr_policy.txt]"*
* **Scoring Breakdown**:
  1. `refusal_passed = True` (Did not refuse valid query).
  2. `retrieval_passed = True` (`acme_hr_policy.txt` present in top-3 chunks).
  3. `grounding_passed = True` (Matched `"10:00"`, `"3:00"`, `"Eastern"`).
  4. `citation_passed = True` (`[Source 1: acme_hr_policy.txt]` cited).
* **Result**: **PASS** (100%).

---

### Example B: Out-of-Scope Guardrail Query (`EVAL-08`)
* **Question**: *"What is Acme's policy regarding interstellar space travel reimbursement?"*
* **Pipeline Output**: *"I do not have sufficient information in the provided documents to answer this question."*
* **Scoring Breakdown**:
  1. `refusal_passed = True` (Detected exact guardrail refusal string).
  2. `retrieval_passed = True` (Ignored for refusal).
  3. `grounding_passed = True` (Refusal was faithful to missing context).
  4. `citation_passed = True` (No phantom citations attached).
* **Result**: **PASS** (100%).

---

## 7. How This Compares to Industry Standards

| Technique | Doc-QA Assistant Approach | Industry Comparison (Ragas / TruLens) |
| :--- | :--- | :--- |
| **Retrieval Scoring** | Exact source file containment check | Context Precision / Hit Rate @ K |
| **Grounding Scoring** | Keyword presence & factual string matching | Faithfulness / Answer Relevance |
| **Refusal Scoring** | Deterministic guardrail string & refusal flag check | Negative Constraint Evaluation |
| **Execution Cost** | **Zero API cost** (local deterministic evaluation) | Often requires an expensive LLM-as-a-judge model |

---

## 8. Algorithmic Logic & Python Implementation

Here is the exact algorithmic logic and Python code from [`app/evaluation/evaluator.py`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/evaluator.py) that toggles each variable:

### 1. How `refusal_passed` is Toggled

The algorithm checks whether the question was **supposed to be refused** (`test_case.should_refuse`):

```python
if test_case.should_refuse:
    # 1. For Out-of-Scope queries (e.g., Space Travel, Stock Predictions)
    refusal_passed = (
        is_refusal 
        or "insufficient information" in answer_text.lower() 
        or "not have sufficient" in answer_text.lower()
    )
else:
    # 2. For Valid Factual queries (e.g., Core Hours, Redis TTL)
    refusal_passed = not is_refusal
```

* **How `is_refusal` is detected**: When the LLM (or offline generator) runs, the system scans the answer for negative constraint triggers:
  ```python
  is_refusal = (
      "do not have sufficient information" in answer.lower()
      or "insufficient information" in answer.lower()
  )
  ```
* If an out-of-scope query triggers the refusal $\rightarrow$ `refusal_passed = True`.
* If the LLM tries to invent an answer for an out-of-scope question $\rightarrow$ `refusal_passed = False`.

---

### 2. How `retrieval_passed` is Toggled

The algorithm compares the **retrieved chunk filenames** against the ground-truth `expected_source_files`:

```python
retrieved_sources = [c.source_filename for c in query_result.retrieved_chunks]

retrieval_passed = True
for expected_doc in test_case.expected_source_files:
    # Check if expected document name is a substring of any retrieved chunk filename
    if not any(expected_doc.lower() in src.lower() for src in retrieved_sources):
        retrieval_passed = False
```

* **Example**: If `expected_source_files = ["acme_hr_policy.txt"]` and ChromaDB retrieved chunks from `["acme_hr_policy.txt", "doc_qa_system_manual.txt"]` $\rightarrow$ `retrieval_passed = True`.

---

### 3. How `grounding_passed` is Toggled

The algorithm uses a **Sub-string Keyword Matching & Threshold Ratio** algorithm:

```python
# 1. Case-insensitive matching of expected factual tokens against the raw answer
matched_keywords = [
    kw for kw in test_case.expected_keywords
    if kw.lower() in answer_text.lower()
]

# 2. Threshold Condition: must match at least 50% (and at least 1) of the expected keywords
threshold = max(1, len(test_case.expected_keywords) // 2)
grounding_passed = len(matched_keywords) >= threshold
```

* **Example**:
  * For Core Hours: `expected_keywords = ["10:00", "3:00", "eastern"]` ($N=3$, threshold = $\max(1, 1) = 1$).
  * If the answer says *"10:00 AM to 3:00 PM Eastern Time"*, `matched_keywords = ["10:00", "3:00", "eastern"]` (3 matched) $\rightarrow 3 \ge 1 \rightarrow$ `grounding_passed = True`.

---

### 4. How `citation_passed` is Toggled

The algorithm verifies whether the response has explicit source provenance:

```python
has_citation = (
    bool(query_result.citations) 
    or "[Source" in answer_text 
    or "[source" in answer_text
)
citation_passed = has_citation
```

* If the model gives a factual answer but forgot to cite where it came from $\rightarrow$ `citation_passed = False`.

---

### 5. Final Composite Decision (`passed`)

The overall status is a strict logical **AND** ($\land$) gate across all 4 criteria:

```python
overall_passed = (
    retrieval_passed 
    and grounding_passed 
    and citation_passed 
    and refusal_passed
)
```

If **any single condition** is `False`, the test case is marked **`FAIL`**, and the exact reason is saved in `failure_reasons` for inspection in the CLI and Web dashboard.

