# Local Edge Model Evaluation & Benchmark Analysis (Ollama / Gemma 3 1B)

**Document Version**: v0.2.0  
**Evaluated Models**: `ollama/gemma3:1b` (Local via Ollama) vs `gemini/gemini-1.5-flash` (Cloud API via LiteLLM)  
**Dataset**: Standardized 10-Question RAG Benchmark Suite (`app/evaluation/test_dataset.py`)

---

## 1. Executive Summary

This evaluation analyzed the behavioral differences, latency profiles, and constraint sensitivity between large cloud-hosted models (`gemini/gemini-1.5-flash`) and ultra-lightweight local edge models (`ollama/gemma3:1b`).

### Comparative Benchmark Results

| Metric | `gemini/gemini-1.5-flash` (Cloud API) | `ollama/gemma3:1b` (Local Ollama) | Delta / Impact |
| :--- | :---: | :---: | :--- |
| **Pass Rate** | **80.0%** (8/10) | **70.0%** (7/10) | -10.0% |
| **Average Latency** | **17,284.9ms** (~17.3s) | **1,111.1ms** (~1.1s) | ⚡ **15.5× Faster** |
| **Retrieval Accuracy** | **100.0%** (10/10) | **100.0%** (10/10) | Identical (MiniLM local vector store) |
| **Refusal Accuracy** | **100.0%** (2/2) | **100.0%** (2/2) | **Zero Hallucinations** |
| **Multi-Doc Synthesis** | **PASS** (EVAL-10) | **PASS** (EVAL-10) | Both synthesized cross-document facts |

---

## 2. In-Depth Analysis of Failure Modes

Across all 10 test cases, `ollama/gemma3:1b` demonstrated **100% retrieval accuracy** and **100% refusal accuracy** (successfully rejecting unsupported queries in EVAL-08 and EVAL-09). The 3 test failures were rooted in **rigid automated test constraints** rather than factual hallucinations.

### 2.1 EVAL-01: Character Ceiling vs Conversational Preamble
* **Question**: *"What are the core collaboration hours at Acme Corporation? Answer in fewer than 100 characters."*
* **Outcome**: `FAIL` (Retrieval: ✔, Grounding: ✔, Refusal: ✔, Length: ✖).
* **Root Cause**: While `gemma3:1b` extracted all expected keywords (`10:00`, `3:00`, `Eastern`), small local models often prepend polite or explanatory phrases (*"Based on the provided context, the core collaboration hours..."*). This caused the total string length to exceed the rigid `max_length = 100` character bound.

### 2.2 EVAL-03: Prompt Conflict in Strict Keyword Recall
* **Question**: *"What is the monthly downtime limit for the 99.99% cloud SLA guarantee? Output only the numerical value and unit."*
* **Test Case Expectation**: `expected_keywords = ["4.38", "downtime", "99.99%"]`, `require_all_keywords = True`.
* **Outcome**: `FAIL` (Grounding: ✖).
* **Root Cause**: The prompt explicitly commanded the model to *"Output only the numerical value and unit"*. When `gemma3:1b` faithfully followed this instruction and responded concisely (e.g. `"4.38 minutes [Source 1]"`), the grounding assertion failed because the keywords `"downtime"` and `"99.99%"` were not present in the output.

### 2.3 EVAL-06: Punctuation & Substring Rigidity
* **Question**: *"Provide the cycle life of LiFePO4 batteries at 80% Depth of Discharge and optimal temperature."*
* **Test Case Expectation**: `expected_keywords = ["6,000", "8,000", "15", "35"]`, `require_all_keywords = True`.
* **Outcome**: `FAIL` (Grounding: ✖).
* **Root Cause**: Number formatting variation. Local models often generate numbers without comma thousand separators (`6000` to `8000` instead of `6,000` to `8,000`). Exact substring checks treated `6000` as a mismatch for `6,000`.

---

## 3. Architectural Recommendations

1. **Flexible Keyword Matchers**:
   - Normalize numeric values and punctuation during grounding evaluation (stripping commas, currency symbols, and whitespace before comparison).
   - Support semantic keyword sets (e.g., matching either `"6,000"` OR `"6000"`, `"4.38"` with optional metric descriptors).
2. **Align Question Instructions with Assertions**:
   - Ensure questions asking for *"only numerical values"* do not enforce mandatory keyword presence of question preamble words.
3. **Adaptive Length Bounds**:
   - Provide reasonable leeway in `max_length` to accommodate citation brackets (`[Source 1]`) and minor model preamble without failing factual accuracy.
