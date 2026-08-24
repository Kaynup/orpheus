# Step 6: Comprehensive Security Model, Guardrails & Compliance

This document provides a detailed technical breakdown of **Step 6** in the **Doc-QA Assistant** RAG pipeline. It covers the end-to-end security architecture, threat model, anti-hallucination guardrails, secret protection, input sanitization, CSP configuration, and compliance verification.

---

## 1. Security Architecture & Trust Boundaries

The Doc-QA Assistant processes external untrusted files, user queries, vector embeddings, and third-party LLM API responses. The security model enforces strict trust boundaries across every boundary:

```
[Untrusted Client / User Query / Uploaded File]
      │
      ▼  Boundary 1: Input Validation & Path Traversal Sanitization (validator.py)
[Sanitized Document / Ingestion Engine]
      │
      ▼  Boundary 2: Local Vector Database Storage (vector_store.py)
[Persistent ChromaDB on Local Disk]
      │
      ▼  Boundary 3: Retrieval Filtering & Distance Thresholding (retriever.py)
[Confidence-Filtered Context Chunks]
      │
      ▼  Boundary 4: Grounded Prompt Augmentation & Guardrails (prompt_builder.py)
[System Instruction Guardrail Sandbox]
      │
      ▼  Boundary 5: Secret-Masked LLM Provider Orchestration (generator.py, logging_config.py)
[Grounded Answer / Guardrail Refusal]
      │
      ▼  Boundary 6: Safe Native DOM Rendering & Zero XSS (app.js, security.py)
[Browser UI Output]
```

---

## 2. Multi-Layered Anti-Hallucination Guardrails

Hallucination in RAG systems occurs when the LLM generates unsupported assertions, extrapolates beyond provided context, or fabricates citations. Doc-QA Assistant implements a **5-layer guardrail defense**:

### Layer 1: Retrieval Confidence Thresholding ([`app/retrieval/retriever.py`](file:///home/remitpe/MAIN/rag-chat/app/retrieval/retriever.py))
* Every retrieved chunk is scored by cosine distance.
* If all retrieved chunks have distance $> 0.90$ (similarity $< 0.10$), the retrieval output is flagged as `has_relevant_context = False`.
* Low-confidence chunks are marked `is_confident = False`.

### Layer 2: Isolated Numbered Source Formatting ([`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py))
* Context chunks are cleanly demarcated with explicit boundaries:
  ```text
  --- [Source 1: acme_hr_policy.txt (Page 1)] ---
  <factual chunk content>
  ```
* Prevents the LLM from confusing multiple documents or mixing unrelated facts.

### Layer 3: Unambiguous Guardrail System Prompt ([`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py))
* Injects mandatory negative constraints into the system prompt:
  * **Rule 1**: Answer ONLY using facts from the retrieved context.
  * **Rule 2**: Every statement must cite its numbered source (`[Source N]`).
  * **Rule 3**: If context is missing, irrelevant, or insufficient, state: *"I do not have sufficient information in the provided documents to answer this question."*
  * **Rule 4**: Do NOT speculate, extrapolate, or use outside training knowledge.

### Layer 4: Fallback Refusal Engine ([`app/generation/generator.py`](file:///home/remitpe/MAIN/rag-chat/app/generation/generator.py))
* In offline mode and API fallback mode, queries that do not match context keywords trigger an immediate deterministic refusal rather than returning partial guesses.

### Layer 5: Absence of Phantom Citations ([`app/generation/generator.py`](file:///home/remitpe/MAIN/rag-chat/app/generation/generator.py))
* When a refusal is triggered (`is_refusal = True`), the system strips source citations from the output, ensuring users are never presented with fake citations on unanswerable questions.

---

## 3. Web & API Security Hardening

### A. Strict Localhost Binding ([`app/main.py`](file:///home/remitpe/MAIN/rag-chat/app/main.py))
* The Flask server strictly binds to `127.0.0.1:5000`.
* The server factory explicitly intercepts and overrides `0.0.0.0` to prevent accidental exposure to external network interfaces.

### B. HTTP Security Headers ([`app/api/security.py`](file:///home/remitpe/MAIN/rag-chat/app/api/security.py))
Every HTTP response automatically receives hardened headers:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
```

* **`X-Frame-Options: DENY`**: Protects users against clickjacking attacks by forbidding the application from being embedded in `<iframe>` or `<frame>` elements.
* **`X-Content-Type-Options: nosniff`**: Prevents browsers from MIME-sniffing a response away from the declared content-type.
* **`Content-Security-Policy`**: Restricts scripts and network connections exclusively to `'self'`.

### C. File Upload Sandboxing & Validation ([`app/ingestion/validator.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/validator.py))
* **Path Traversal Defense**: Filenames are sanitized using `Path(normalized).name.lstrip(".")` and sanitized character whitelisting. Sequences like `../../etc/passwd` are reduced to `passwd`.
* **Magic Byte Validation**:
  * `.pdf` uploads must start with the `%PDF-` binary header.
  * `.txt` uploads must be valid UTF-8/ASCII decodable text.
* **File Size Cap**: Enforces a strict 10 MB maximum limit (`MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024`).

### D. Pure Native DOM Manipulation (Zero XSS) ([`app/static/js/app.js`](file:///home/remitpe/MAIN/rag-chat/app/static/js/app.js))
* All dynamic content (chat messages, citation pills, evaluation results, file metadata, error strings) is injected using:
  * `element.textContent = ...`
  * `document.createElement(...)`
  * `parent.replaceChildren(...)`
* The frontend completely avoids `innerHTML` on untrusted user strings, preventing Cross-Site Scripting (XSS).

---

## 4. Secret Protection & Log Masking

### Secret Scrubbing ([`app/logging_config.py`](file:///home/remitpe/MAIN/rag-chat/app/logging_config.py))
`SecretMaskingFormatter` intercepts all logging output and scrubs API keys matching regular expression patterns:

```python
SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{35})"),              # Google / Gemini keys
    re.compile(r"(sk-or-v1-[0-9a-fA-F]{64})"),          # OpenRouter keys
    re.compile(r"(sk-[a-zA-Z0-9]{32,})"),               # OpenAI keys
    re.compile(r"(Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*)"), # HTTP Bearer tokens
]
```

* Any matching string in console output or log files is replaced with `[REDACTED_SECRET]`.
* Environment variables are loaded strictly via `python-dotenv` into strongly-typed `LLMConfig` instances and never logged in plain text.

---

## 5. Security Verification & Compliance Tests

Security controls are verified automatically via dedicated test cases:

| Test Module | Security Property Verified |
| :--- | :--- |
| **`tests/test_api_security.py`** | Validates CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`. |
| **`tests/test_api_security.py`** | Validates HTTP 400 rejection on malicious/unsupported upload file types. |
| **`tests/test_ingestion.py`** | Validates path traversal sanitization (`../../../etc/passwd` -> `passwd`). |
| **`tests/test_ingestion.py`** | Validates rejection of empty files and non-existent paths. |
| **`tests/test_pipeline.py`** | Validates anti-hallucination guardrail triggering on out-of-scope queries. |
| **`tests/test_evaluation.py`** | Validates refusal detection accuracy in benchmark evaluation. |

---

## 6. Summary of Step 6 Deliverables

| Security Layer | Implemented Safeguards | Primary Source File |
| :--- | :--- | :--- |
| **Guardrails** | Distance thresholding, numbered context, refusal detection | [`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py) |
| **Headers** | CSP, `X-Frame-Options: DENY`, `nosniff` | [`app/api/security.py`](file:///home/remitpe/MAIN/rag-chat/app/api/security.py) |
| **Ingestion** | Path sanitization, magic bytes, 10MB size limit | [`app/ingestion/validator.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/validator.py) |
| **Network** | Strict `127.0.0.1:5000` binding | [`app/main.py`](file:///home/remitpe/MAIN/rag-chat/app/main.py) |
| **Frontend** | Pure DOM APIs (`textContent`, `replaceChildren`), zero XSS | [`app/static/js/app.js`](file:///home/remitpe/MAIN/rag-chat/app/static/js/app.js) |
| **Secrets** | Regex masking for Gemini, OpenRouter, OpenAI, and Bearer keys | [`app/logging_config.py`](file:///home/remitpe/MAIN/rag-chat/app/logging_config.py) |
| **Testing** | Dedicated automated security test suite | [`tests/test_api_security.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_api_security.py) |
