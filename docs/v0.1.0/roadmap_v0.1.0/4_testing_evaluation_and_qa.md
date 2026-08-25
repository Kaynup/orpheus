# Automated Testing, Benchmark Evaluation & Quality Assurance

This document provides a detailed technical breakdown of the RAG pipeline. It covers the full test suite architecture, automated benchmark evaluation, regression testing, and quality assurance workflows.

---

## 1. Architectural Goal & Flow

Provides rigorous, automated verification across every layer of the Doc-QA Assistant—from individual unit functions (filename sanitization, chunking math) to end-to-end RAG pipelines, API security headers, and evaluation benchmark grading.

```
[Pytest Automated Test Suite]
      ├── Unit Tests: Ingestion, Chunking, Vector Store
      ├── Integration Tests: End-to-End RAG Pipeline & Guardrails
      ├── Security Tests: API Headers, CSP, Upload Sandboxing
      │
[Automated Benchmark Evaluation Engine]
      ├── Retrieval Accuracy Verification
      ├── Grounding Faithfulness Verification
      ├── Source Citation Verification
      └── Anti-Hallucination Refusal Verification
```

---

## 2. Test Suite Architecture ([`tests/`](file:///home/remitpe/MAIN/rag-chat/tests/))

The project includes 18 automated tests organized across 7 test modules:

```
tests/
├── conftest.py               # Shared fixtures, SQLite shims, and test configurations
├── test_ingestion.py         # File validation, sanitization, and parsing tests
├── test_chunking.py          # Boundary-aware splitting and overlap tests
├── test_vector_store.py      # Persistent ChromaDB client and vector search tests
├── test_retrieval.py         # Semantic retrieval and distance threshold tests
├── test_pipeline.py          # End-to-end RAG execution and guardrail tests
├── test_evaluation.py        # Automated benchmark scoring and metric tests
└── test_api_security.py      # HTTP security headers and REST endpoint tests
```

---

## 3. Deep Dive: Test Modules & Coverage

### A. Ingestion & Validation Tests ([`tests/test_ingestion.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_ingestion.py))

* **`test_sanitize_filename`**:
  * Tests that path traversal attacks (`../../etc/passwd`, `..\..\secret.txt`) are stripped to safe filenames (`passwd`, `secret.txt`).
  * Verifies space and character normalization.
* **`test_validate_nonexistent_file`**:
  * Verifies that attempting to validate a non-existent path raises `FileNotFoundError`.
* **`test_validate_empty_file`**:
  * Verifies that empty (0-byte) files are rejected with `ValueError`.
* **`test_validate_invalid_extension`**:
  * Verifies that unauthorized file extensions (`.exe`, `.py`, `.sh`) are rejected.
* **`test_parse_valid_txt`**:
  * Tests that plain text files are parsed with correct page numbers, character counts, and cryptographic SHA-256 checksums.

---

### B. Chunking & Provenance Tests ([`tests/test_chunking.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_chunking.py))

* **`test_chunking_provenance`**:
  * Verifies that each `TextChunk` carries all required provenance fields: `chunk_id`, `chunk_index`, `start_char`, `end_char`, `page_number`, `source_filename`, `doc_id`, and `token_count_estimate`.
* **`test_chunking_overlap_constraint`**:
  * Tests the `ChunkConfig` validation rule: setting `chunk_overlap >= chunk_size` raises a `ValueError`.
  * Verifies that adjacent chunks share text across paragraph/sentence boundaries.

---

### C. Vector Store Tests ([`tests/test_vector_store.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_vector_store.py))

* **`test_vector_store_add_and_search`**:
  * Uses `tmp_path` to spin up an isolated ChromaDB persistent instance.
  * Adds sample chunks, computes 384-dimensional embeddings, and executes a semantic nearest-neighbor search.
  * Verifies that cosine distances and similarities are calculated correctly.
* **`test_vector_store_list_and_delete`**:
  * Ingests multiple documents and checks `list_documents()` aggregation.
  * Tests `delete_document(doc_id)` to ensure all associated chunk vectors and metadata are removed.

---

### D. Semantic Retrieval Tests ([`tests/test_retrieval.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_retrieval.py))

* **`test_retrieval_matches_relevant_chunk`**:
  * Queries the retriever with a semantic question and verifies that the top-ranked chunk matches the intended context with high similarity ($\ge 0.70$).
* **`test_retrieval_empty_query`**:
  * Verifies that submitting empty or whitespace-only queries raises a `ValueError`.

---

### E. End-to-End Pipeline Tests ([`tests/test_pipeline.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_pipeline.py))

* **`test_pipeline_supported_query`**:
  * Executes a complete RAG workflow for a supported document fact.
  * Verifies that the answer is generated, sources are cited, and `is_refusal` is `False`.
* **`test_pipeline_unsupported_query_guardrail`**:
  * Queries the pipeline with an out-of-scope question (e.g. asking for facts not present in the indexed documents).
  * Verifies that the anti-hallucination guardrail triggers, `is_refusal` is `True`, and the standard refusal statement is returned: *"I do not have sufficient information in the provided documents to answer this question."*

---

### F. Evaluation Engine Tests ([`tests/test_evaluation.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_evaluation.py))

* **`test_evaluator_scoring`**:
  * Evaluates a synthetic test case through the evaluator.
  * Verifies retrieval matching, keyword presence checking, citation validation, and refusal logic.
  * Checks aggregation of pass rate percentages and average latency.

---

### G. API & Security Tests ([`tests/test_api_security.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_api_security.py))

* **`test_security_headers_present`**:
  * Inspects HTTP response headers for `Content-Security-Policy`, `X-Frame-Options: DENY`, and `X-Content-Type-Options: nosniff`.
* **`test_api_status_endpoint`**:
  * Verifies that `GET /api/status` returns valid JSON with ChromaDB statistics and active configuration.
* **`test_api_query_empty`**:
  * Verifies that `POST /api/query` rejects empty request bodies with HTTP 400.
* **`test_api_upload_invalid_type`**:
  * Verifies that `POST /api/ingest` rejects unauthorized file formats with HTTP 400.

---

## 4. Automated Benchmark Framework ([`app/evaluation/`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/))

The evaluation benchmark provides objective, repeatable grading of the RAG pipeline:

### Diagnostic Grading Criteria:
1. **Retrieval Accuracy**: The top retrieved chunks must contain the expected ground-truth document.
2. **Grounding Faithfulness**: The generated response must contain all key factual terms present in the context.
3. **Citation Validity**: Factual answers must cite the correct `[Source N]` reference.
4. **Refusal Precision**: Out-of-scope questions must trigger the anti-hallucination guardrail without hallucinating facts.
5. **Latency Profiling**: Millisecond tracking of end-to-end execution.

### Running the Benchmark:
```bash
# Via CLI:
python cli.py evaluate

# Via Makefile:
make eval

# Via Web Interface:
# Navigate to the 'Evaluation Benchmark' tab and click 'Run Full Benchmark'
```

---

## 5. Summary of Step 4 Deliverables

| Deliverable | Description | Location |
| :--- | :--- | :--- |
| **Pytest Suite** | 18 unit, integration, and security tests | [`tests/`](file:///home/remitpe/MAIN/rag-chat/tests/) |
| **Pytest Config** | Test runner configuration with `pythonpath = .` | [`pytest.ini`](file:///home/remitpe/MAIN/rag-chat/pytest.ini) |
| **Benchmark Suite** | Diagnostic test cases & automated evaluator | [`app/evaluation/`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/) |
| **Task Automation** | Common make targets (`test`, `eval`, `run`, `run-cli`) | [`Makefile`](file:///home/remitpe/MAIN/rag-chat/Makefile) |
