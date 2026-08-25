# v0.2.0 Architecture Review: Fixes & Changes Backlog

This document systematically logs all architectural, modularity, coupling, and cohesion issues identified during the review of the roadmap and codebase for **Step 1: Document Ingestion, Chunking & Persistent Vector Storage**.

---

## Architecture Goals for v0.2.0
* **Low Coupling**: Submodules should not hardcode assumptions about each other's configurations, metrics, or formats.
* **High Cohesion**: Each module must have a single, well-defined responsibility.
* **Open-Closed Principle (OCP)**: Adding new file formats or embedding models should not require modifying existing parsing loops or storage classes.
* **Single Source of Truth**: All operational limits (file sizes, allowed extensions, buffer sizes, distance metrics) must be driven by `AppConfig` and `.env`.

---

## Step 1 (Ingestion & Storage) Backlog

### 1. `app/ingestion/validator.py`

* **`[FIX-INGEST-01]` Config-Driven File Size Limit**
  * **Category**: `fix`
  * **Current State**: `MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024` (10 MB) is hardcoded at module level.
  * **Limitation**: Ignores `ServerConfig.max_content_length` and environment variables. If a user increases the limit in `.env`, the validator still rejects files over 10 MB.
  * **Proposed Fix**: Derive `max_file_size_bytes` dynamically from `config.storage.max_file_size_bytes` or `config.server.max_content_length`, allowing overrides in function calls: `validate_file(path, max_bytes=...)`.

* **`[REFACTOR-INGEST-02]` Decouple Allowed Extensions via Configuration**
  * **Category**: `refactor`
  * **Current State**: `ALLOWED_EXTENSIONS = {".txt", ".pdf"}` is hardcoded as a module constant.
  * **Limitation**: Any new parser format (e.g. Markdown `.md`, Word `.docx`) requires editing `validator.py` directly.
  * **Proposed Fix**: Move `allowed_extensions` to `StorageConfig` (loaded from `RAG_ALLOWED_EXTENSIONS="txt,pdf"` in `.env`) or dynamically discover them from the Parser Registry.

---

### 2. `app/ingestion/parser.py`

* **`[FIX-INGEST-03]` Configurable I/O Buffer for Checksum Calculation**
  * **Category**: `fix`
  * **Current State**: Line 52 hardcodes `f.read(65536)` (64 KB).
  * **Limitation**: Hardcoded buffer constant without descriptive naming or tuning capability for high-throughput stream environments.
  * **Proposed Fix**: Define an explicit constant `DEFAULT_HASH_BUFFER_SIZE = 65536` or allow custom buffer sizes in `compute_sha256(path, buffer_size=...)`.

* **`[REFACTOR-INGEST-04]` Implement Parser Strategy Registry (OCP Compliance)**
  * **Category**: `refactor`
  * **Current State**: `parse_document()` uses hardcoded `if ext == ".txt": ... elif ext == ".pdf": ...` branching.
  * **Limitation**: High coupling. Adding a new file parser requires modifying `parse_document()` and `validator.py`.
  * **Proposed Fix**: Implement a **Parser Strategy Registry** pattern:
    ```python
    class BaseDocumentParser(ABC):
        @abstractmethod
        def parse(self, path: Path) -> ParsedDocument: ...

    PARSER_REGISTRY: Dict[str, BaseDocumentParser] = {
        ".txt": TXTDocumentParser(),
        ".pdf": PDFDocumentParser(),
    }
    ```
    `parse_document()` queries the registry, allowing new parsers (e.g. `.md`, `.docx`, `.csv`) to be registered dynamically without modifying core dispatch code.

---

### 3. `app/chunking/text_splitter.py`

* **`[REFACTOR-CHUNK-01]` Configurable Text Splitter Separator Hierarchy**
  * **Category**: `refactor`
  * **Current State**: `_split_page()` hardcodes separators `["\n\n", "\n", ". ", "? ", "! ", " ", ""]` inside the method.
  * **Limitation**: Different document formats (e.g. Markdown headers `##`, Python code `def `, HTML tags `<p>`) require custom boundary hierarchies that cannot currently be customized.
  * **Proposed Fix**: Add `separators: Optional[List[str]] = None` to `ChunkConfig` with default fallback to standard paragraph/sentence separators.

* **`[REFACTOR-CHUNK-02]` Decouple Token Estimation**
  * **Category**: `refactor`
  * **Current State**: `len(content) // 4` is embedded directly in chunk generation.
  * **Limitation**: Coarse estimation cannot be swapped with domain-specific tokenizers (e.g. `tiktoken`, HuggingFace tokenizers).
  * **Proposed Fix**: Encapsulate token counting into a dedicated helper `estimate_tokens(text: str) -> int` or pluggable tokenizer callable.

---

### 4. `app/embedding/embedder.py`

* **`[FIX-EMBED-01]` Pluggable Embedding Function Resolution**
  * **Category**: `fix`
  * **Current State**: `EmbeddingManager` accepts `model_name: str = "all-MiniLM-L6-v2"`, but unconditionally instantiates `ef.DefaultEmbeddingFunction()`.
  * **Limitation**: Changing `model_name` in `config.py` has no effect on the underlying Chroma embedding function.
  * **Proposed Fix**: Inspect `model_name` and instantiate the appropriate Chroma embedding function (e.g. `ONNXMiniLM_L6_V2`, `SentenceTransformerEmbeddingFunction`, or `OpenAIEmbeddingFunction`).

* **`[REFACTOR-EMBED-02]` Expose Embedding Metadata & Metric Abstractions**
  * **Category**: `refactor`
  * **Current State**: Vector dimension (384) and distance space (cosine) are assumed implicitly by downstream modules.
  * **Limitation**: Downstream storage and retrieval classes are tightly coupled to 384-d cosine space assumptions.
  * **Proposed Fix**: Expose explicit metadata properties on `EmbeddingManager`:
    * `dimension: int`
    * `distance_metric: str` (e.g. `"cosine"`, `"l2"`, `"ip"`)
    * `distance_to_similarity(distance: float) -> float`

---

### 5. `app/storage/vector_store.py`

* **`[FIX-STORE-01]` Dynamic Collection Distance Space Configuration**
  * **Category**: `fix`
  * **Current State**: Line 63 and Line 303 hardcode `metadata={"hnsw:space": "cosine"}`.
  * **Limitation**: Binds Chroma collection space to cosine distance, ignoring embedding manager specifications or configuration overrides.
  * **Proposed Fix**: Derive HNSW space from `self.embedding_manager.distance_metric` or `config.storage.hnsw_space`.

* **`[REFACTOR-STORE-02]` Metric-Agnostic Similarity Calculation**
  * **Category**: `refactor`
  * **Current State**: Lines 183–185 calculate `similarity = max(0.0, 1.0 - float(distance))` with hardcoded comments assuming cosine distance.
  * **Limitation**: If an alternate distance metric (e.g. L2 distance or inner product) is used, this formula produces invalid similarity percentages.
  * **Proposed Fix**: Delegate similarity conversion to `self.embedding_manager.distance_to_similarity(distance)` or a dedicated metric mapper.

* **`[REFACTOR-STORE-03]` Safe Batch Insertion for Large Documents**
  * **Category**: `refactor`
  * **Current State**: `add_chunks()` pushes the entire `chunks` list into `self._collection.add()` in a single call.
  * **Limitation**: Large documents generating thousands of chunks risk exceeding ChromaDB's maximum batch size.
  * **Proposed Fix**: Process chunk persistence in safe batches of `BATCH_SIZE = 1000`.

---

### 6. `app/config.py` & `.env.example`

* **`[FEAT-CONFIG-01]` Add Storage & Extension Settings to `StorageConfig`**
  * **Category**: `feat`
  * **Current State**: `StorageConfig` only contains directory paths and collection name.
  * **Proposed Additions**:
    * `allowed_extensions: List[str] = field(default_factory=lambda: [".txt", ".pdf"])`
    * `max_file_size_bytes: int = 10 * 1024 * 1024`
    * `distance_metric: str = "cosine"`
    * `batch_size: int = 1000`

---

## Summary of Step 1 Review

| ID | Module | Category | Description | Priority |
| :--- | :--- | :--- | :--- | :--- |
| `FIX-INGEST-01` | `validator.py` | `fix` | Connect file size limits to configuration | High |
| `REFACTOR-INGEST-02` | `validator.py` | `refactor` | Decouple allowed extensions via config | High |
| `FIX-INGEST-03` | `parser.py` | `fix` | Named constant for hash buffer size | Low |
| `REFACTOR-INGEST-04` | `parser.py` | `refactor` | Implement Parser Strategy Registry pattern | High |
| `REFACTOR-CHUNK-01` | `text_splitter.py` | `refactor` | Configurable boundary separator list | Medium |
| `REFACTOR-CHUNK-02` | `text_splitter.py` | `refactor` | Pluggable token estimator helper | Low |
| `FIX-EMBED-01` | `embedder.py` | `fix` | Dynamic embedding function resolution | Medium |
| `REFACTOR-EMBED-02` | `embedder.py` | `refactor` | Expose dimension & metric helper methods | High |
| `FIX-STORE-01` | `vector_store.py` | `fix` | Dynamic HNSW space from embedding manager | Medium |
| `REFACTOR-STORE-02` | `vector_store.py` | `refactor` | Metric-agnostic similarity conversion | Medium |
| `REFACTOR-STORE-03` | `vector_store.py` | `refactor` | Safe batching for chunk insertion | Medium |
| `FEAT-CONFIG-01` | `config.py` | `feat` | Add storage settings to `StorageConfig` | High |

---

## Step 2 (Retrieval, Generation & CLI) Backlog

### 7. `app/retrieval/retriever.py`

* **`[REFACTOR-RETRIEVAL-01]` Remove Metric-Specific Comments**
  * **Category**: `refactor`
  * **Current State**: Lines 122–123 contain comments specifically mentioning cosine distance thresholds (e.g., `<= 0.85`).
  * **Limitation**: The comments are misleading if the user configures the embedding manager to use L2 or Inner Product metric spaces.
  * **Proposed Fix**: Remove hardcoded metric assumptions in comments and rely on the metric-agnostic threshold validation logic mapped from the config.

---

### 8. `app/augmentation/prompt_builder.py`

* **`[FEAT-PROMPT-01]` Extract Prompts into Versioned Assets**
  * **Category**: `feat`
  * **Current State**: `SYSTEM_INSTRUCTION` and the full prompt templates are hardcoded Python strings.
  * **Limitation**: Prompts cannot be version-controlled independently of the codebase (high coupling).
  * **Proposed Fix**: Create an asset directory structure (e.g., `assets/prompts/system-prompts/` and `assets/prompts/full-prompt-templates/`). Store prompts in files named securely (e.g., `<version>_<name>_<incremental_number>.txt`). Load these dynamically inside `PromptBuilder`.

---

### 9. `app/generation/generator.py`

* **`[FIX-GEN-01]` Configurable Telemetry Suppression**
  * **Category**: `fix`
  * **Current State**: Line 27 hardcodes `litellm.suppress_debug_info = True`.
  * **Limitation**: Users cannot enable LiteLLM telemetry for deep debugging without altering the source code.
  * **Proposed Fix**: Toggle `litellm.suppress_debug_info` based on `config.server.debug` or a specific environment variable like `LLM_DEBUG_INFO`.

* **`[REFACTOR-GEN-02]` Extract Refusal Texts to Asset Directory**
  * **Category**: `refactor`
  * **Current State**: Line 115 and line 316 hardcode refusal texts and fallback notes as Python strings.
  * **Limitation**: Hard to debug, localize, or adapt refusal boundaries without modifying python execution files.
  * **Proposed Fix**: Move these constant strings to an official `assets/configs/` directory.

* **`[REFACTOR-GEN-03]` Extract NLP Stopwords and Anchor Terms to Assets**
  * **Category**: `refactor`
  * **Current State**: `stopwords` and `anchor_terms` sets are hardcoded inside `_generate_offline_response()`.
  * **Limitation**: Prevents adding new custom anchors without modifying the execution logic.
  * **Proposed Fix**: Load stopwords and anchor terms from a JSON/TXT file in the `assets/` directory.

* **`[FIX-GEN-04]` Configurable Offline Topic Threshold**
  * **Category**: `fix`
  * **Current State**: Lines 157-158 hardcode the relevance fallback threshold at `0.4` (40%).
  * **Limitation**: Binds the offline fallback engine to an arbitrary constraint that ignores configuration parameters.
  * **Proposed Fix**: Move the `0.4` threshold to `RetrievalConfig` or `LLMConfig` to be tuned via `.env`.

* **`[FIX-GEN-05]` Respect Offline Sentence Limits**
  * **Category**: `fix`
  * **Current State**: Line 199 hardcodes the fallback generation to `matched_sentences[:4]`.
  * **Limitation**: Silently nullifies environmental configurations for response length.
  * **Proposed Fix**: Control fallback sentence limits using `LLMConfig.max_tokens` or a specific offline sentence limit parameter.

---

### 10. `cli.py`

* **`[REFACTOR-CLI-01]` Centralize and De-Genericize Emojis**
  * **Category**: `refactor`
  * **Current State**: Emojis (e.g., ⏳, ⚡, ✅, ❌) are generic and hardcoded directly within functions.
  * **Limitation**: To change visual branding, one must hunt down emojis scattered across `cli.py`.
  * **Proposed Fix**: Centralize all UI/CLI characters into a unified `UI_THEME` dictionary or asset file, and use more specific/professional icons.

---

## Summary of Step 2 Review

| ID | Module | Category | Description | Priority |
| :--- | :--- | :--- | :--- | :--- |
| `REFACTOR-RETRIEVAL-01` | `retriever.py` | `refactor` | Remove metric-specific cosine comments | Low |
| `FEAT-PROMPT-01` | `prompt_builder.py` | `feat` | Extract prompts into versioned `assets/prompts/` | High |
| `FIX-GEN-01` | `generator.py` | `fix` | Configurable LiteLLM telemetry suppression | Medium |
| `REFACTOR-GEN-02` | `generator.py` | `refactor` | Extract refusal texts to `assets/configs/` | High |
| `REFACTOR-GEN-03` | `generator.py` | `refactor` | Extract stopwords and anchor terms to `assets/` | High |
| `FIX-GEN-04` | `generator.py` | `fix` | Configurable offline topic threshold (40%) | Medium |
| `FIX-GEN-05` | `generator.py` | `fix` | Respect offline sentence limits via config | High |
| `REFACTOR-CLI-01` | `cli.py` | `refactor` | Centralize and upgrade CLI UI theme/emojis | Low |

---

## Step 3 (Web Interface, REST/SSE APIs & Modular UI) Backlog

### 11. `app/main.py` & `app/api/security.py`

* **`[FEAT-API-01]` Flask-CORS Integration with Strict Origin Whitelisting**
  * **Category**: `feat`
  * **Current State**: No Cross-Origin Resource Sharing (CORS) headers configured.
  * **Limitation**: Decoupled frontends (e.g., Next.js/Vite apps or local developer tools) cannot communicate with the Flask REST/SSE API endpoints.
  * **Proposed Fix**: Integrate `flask-cors` in `app/api/security.py` and `app/main.py`. Configure strict origin whitelisting:
    * Default allowed origins: `["http://127.0.0.1:5000", "http://localhost:5000", "http://127.0.0.1:3000", "http://localhost:3000"]`
    * Configurable via `ServerConfig.cors_origins` from `.env`.

---

### 12. `app/static/js/` (Frontend JavaScript Architecture)

* **`[REFACTOR-UI-01]` Deconstruct Monolithic `app.js` into Hierarchical Modular ES6 Modules**
  * **Category**: `refactor`
  * **Current State**: `app.js` is a single 676-line monolithic script managing all state, DOM rendering, SSE streaming, file uploads, and evaluation tables.
  * **Limitation**: High coupling and low cohesion. Adding features to the chat or evaluation dashboard risks breaking unrelated ingestion or tab logic.
  * **Proposed Fix**: Restructure frontend JavaScript into clean, highly cohesive ES6 component modules:
    ```
    app/static/js/
    ├── app.js                      # Application bootstrap & tab navigation router
    ├── modules/
    │   ├── api.js                  # Centralized REST & SSE transport client
    │   └── state.js                # Shared client state & event bus
    └── components/
        ├── chat.js                 # Chat messages, citations, query submission
        ├── inspector.js            # Live pipeline stepper & inspector drawer
        ├── ingestion.js            # Drag-and-drop upload, chunk params, doc listing
        ├── evaluation.js           # Benchmark execution, metrics cards, table rendering
        └── modal.js                # Reusable inspector detail modal
    ```

---

### 13. `templates/` (HTML Template Structure)

* **`[REFACTOR-UI-02]` Modularize Jinja2 Templates into Partials & Layout**
  * **Category**: `refactor`
  * **Current State**: `index.html` is a monolithic 422-line template containing all views, forms, modals, and navigation.
  * **Limitation**: Monolithic template makes maintaining UI sections cumbersome and error-prone.
  * **Proposed Fix**: Break `templates/` into reusable partials and a clean base layout:
    ```
    templates/
    ├── base.html                   # Shell layout (HTML head, CSS/JS links, typography)
    ├── index.html                  # Main container extending base.html
    └── partials/
        ├── header.html             # Navbar, DB status, and version badge
        ├── tab_chat.html           # Chat input, message feed, and inspector panel
        ├── tab_ingestion.html      # Dropzone upload form & indexed documents table
        ├── tab_evaluation.html     # Benchmark metrics grid & test case results
        └── modal_inspector.html    # Step details inspection modal
    ```

---

### 14. `app/static/css/` (CSS Modularization)

* **`[REFACTOR-UI-03]` Component-Based CSS Modularization**
  * **Category**: `refactor`
  * **Current State**: `style.css` holds all global design tokens, resets, component styles, animations, and media queries in a single 500-line file.
  * **Limitation**: Low style cohesion and difficulty theming or updating individual panels.
  * **Proposed Fix**: Organize stylesheets by domain with `@import` in `style.css`:
    ```
    app/static/css/
    ├── style.css                   # Master stylesheet importing component styles
    ├── base.css                    # Earthy color tokens, CSS reset, typography
    ├── layout.css                  # Navbar, tabs, containers, grid layouts
    ├── components/
    │   ├── chat.css                # Message bubbles, citation pills, stepper timeline
    │   ├── ingestion.css           # Dropzone, upload controls, document cards
    │   ├── evaluation.css          # Metric cards, status badges, test tables
    │   └── modal.css               # Modal backdrop and dialog cards
    ```

---

### 15. `app/api/routes.py`

* **`[REFACTOR-API-02]` Decouple Global Pipeline Singleton via Factory / Dependency Injection**
  * **Category**: `refactor`
  * **Current State**: Line 23 instantiates `rag_pipeline = RAGPipeline()` as a global module variable.
  * **Limitation**: Tightly couples API routes to a singleton instance, preventing clean test isolation and custom pipeline configurations.
  * **Proposed Fix**: Inject the pipeline via Flask app extension context (`current_app.extensions['pipeline']` or `get_pipeline()`).

---

## Summary of Step 3 Review

| ID | Module | Category | Description | Priority |
| :--- | :--- | :--- | :--- | :--- |
| `FEAT-API-01` | `main.py` / `security.py` | `feat` | Flask-CORS integration with strict origin whitelist | High |
| `REFACTOR-UI-01` | `static/js/` | `refactor` | Modularize `app.js` into ES6 component modules | High |
| `REFACTOR-UI-02` | `templates/` | `refactor` | Split `index.html` into Jinja2 partials & base layout | High |
| `REFACTOR-UI-03` | `static/css/` | `refactor` | Component-based CSS structure with design tokens | Medium |
| `REFACTOR-API-02` | `routes.py` | `refactor` | Decouple global `RAGPipeline` singleton | Medium |

---

## Step 4 (Testing, Evaluation & Quality Assurance) Backlog

### 16. `tests/` (Test Architecture & Restructuring)

* **`[REFACTOR-TEST-01]` Collocate Unit and Security Tests with Source Modules**
  * **Category**: `refactor`
  * **Current State**: All test files are placed flat in the `tests/` root directory.
  * **Limitation**: Hard to debug, scale, and maintain cohesion. Developers have to context-switch between disparate directory trees.
  * **Proposed Fix**: Restructure tests to be collocated with their respective backend/frontend modules, keeping only integration tests central:
    * **Backend Unit Tests**: Move to `app/<module>/tests/` (e.g., `app/ingestion/tests/test_validator.py`, `app/retrieval/tests/`).
    * **API Security Tests**: Move to `app/api/tests/` (e.g., `test_csp_headers.py`, `test_path_traversal.py`).
    * **Frontend Tests**: Move to `app/static/js/tests/` (for DOM rendering, SSE handling, XSS protection).
    * **Integration Tests**: Keep in `tests/integration/` for end-to-end multi-stage pipeline tests.

* **`[FEAT-TEST-02]` Frontend Unit & Security Testing Suite**
  * **Category**: `feat`
  * **Current State**: Zero automated client-side testing for browser JavaScript.
  * **Limitation**: Relies entirely on manual verification for DOM manipulation safety and XSS prevention.
  * **Proposed Fix**: Add client-side test automation (e.g., using Vitest / Node.js test runner with JSDOM) in `app/static/js/tests/` to test safe `textContent` rendering, citation pill creation, and SSE event streaming logic.

---

### 17. `app/evaluation/` & Sample Corpus

* **`[FEAT-EVAL-01]` Robust Benchmark Test Suite Expansion**
  * **Category**: `feat`
  * **Current State**: `BENCHMARK_TEST_SUITE` contains basic, easily solvable factual questions.
  * **Limitation**: Gives the LLM too easy of a task, failing to stress-test context boundaries or response length limits.
  * **Proposed Fix**: Increase the robustness of the existing evaluation benchmark parameters. Without inventing entirely new paradigms, make the test assertions and prompts stricter (e.g., tighter topic thresholds, strict character limits, and demanding multi-document synthesis constraints).

* **`[DOC-EVAL-02]` Enrich Sample Documents Corpus (`data/sample_documents/`)**
  * **Category**: `doc`
  * **Current State**: Sample files are concise single-topic plain text files.
  * **Limitation**: Simple documents don't reflect real-world, complex scenarios for the chunker and retriever to solve.
  * **Proposed Fix**: Update and expand `data/sample_documents/` with highly detailed, up-to-date, and elaborative real-world documents. Use web search to fetch rich content (e.g., technical specs, lengthy policies) to create a robust playground for testing retrieval efficacy.

---

## Summary of Step 4 Review

| ID | Module | Category | Description | Priority |
| :--- | :--- | :--- | :--- | :--- |
| `REFACTOR-TEST-01` | `tests/` | `refactor` | Collocate unit/security tests within component dirs | High |
| `FEAT-TEST-02` | `app/static/js/tests/` | `feat` | Add automated frontend unit and security test suite | High |
| `FEAT-EVAL-01` | `evaluation/` | `feat` | Make benchmark parameters and test cases robust | High |
| `DOC-EVAL-02` | `sample_documents/` | `doc` | Enrich sample corpus with detailed, up-to-date web data | Medium |

---

## v0.2.0 Implementation Branch Strategy

To maintain a clean Git history and ensure isolated, reviewable changes, the backlog above will be implemented using the following branch structure.

### Commit Message Convention

Each branch is committed with a **single, small, one-line commit message** at the end of its implementation. Commit messages must follow this format:

```
<type>(<scope>): <short imperative summary>
```

| Field | Rule |
| :--- | :--- |
| `type` | Must match the branch category: `feat`, `fix`, `refactor`, `doc`, `test`, `chore` |
| `scope` | The primary module or file area changed (e.g., `ingestion`, `config`, `generator`, `ui`) |
| `summary` | Lowercase, imperative, ≤ 72 characters, no period at the end |

**Examples:**
* `refactor(ingestion): make validator limits and extensions config-driven`
* `feat(api): add Flask-CORS with strict localhost origin whitelist`
* `refactor(ui): split app.js into ES6 component modules`
* `test(ingestion): add unit coverage for parser registry and config limits`

---

### Step 1 Branches (Ingestion & Storage)
* `v0.2/refactor/ingestion-module` (Covers `FIX-INGEST-01`, `REFACTOR-INGEST-02`, `FIX-INGEST-03`, `REFACTOR-INGEST-04`)
  * **Commit:** `refactor(ingestion): make file limits config-driven and introduce parser registry`
* `v0.2/refactor/chunking-module` (Covers `REFACTOR-CHUNK-01`, `REFACTOR-CHUNK-02`)
  * **Commit:** `refactor(chunking): make separators config-driven and decouple token estimation`
* `v0.2/refactor/embedding-module` (Covers `FIX-EMBED-01`, `REFACTOR-EMBED-02`)
  * **Commit:** `refactor(embedding): dynamically resolve embedding model and expose metric properties`
* `v0.2/refactor/vector-store` (Covers `FIX-STORE-01`, `REFACTOR-STORE-02`, `REFACTOR-STORE-03`)
  * **Commit:** `refactor(storage): make similarity calculation metric-agnostic and implement safe chunk batching`
* `v0.2/feat/storage-config` (Covers `FEAT-CONFIG-01`)
  * **Commit:** `feat(config): add distance metric and batch size variables to storage config`

### Step 2 Branches (Retrieval, Generation & CLI)
* `v0.2/refactor/retrieval-module` (Covers `REFACTOR-RETRIEVAL-01`)
  * **Commit:** `refactor(retrieval): remove hardcoded metric assumptions in semantic proximity threshold comments`
* `v0.2/feat/versioned-prompts` (Covers `FEAT-PROMPT-01`)
* `v0.2/refactor/generation-module` (Covers `FIX-GEN-01`, `REFACTOR-GEN-02`, `REFACTOR-GEN-03`, `FIX-GEN-04`, `FIX-GEN-05`)
* `v0.2/refactor/cli-theme` (Covers `REFACTOR-CLI-01`)

### Step 3 Branches (Web Interface & API)
* `v0.2/feat/flask-cors` (Covers `FEAT-API-01`)
* `v0.2/refactor/frontend-js-modules` (Covers `REFACTOR-UI-01`)
* `v0.2/refactor/frontend-templates` (Covers `REFACTOR-UI-02`)
* `v0.2/refactor/frontend-css` (Covers `REFACTOR-UI-03`)
* `v0.2/refactor/api-pipeline-singleton` (Covers `REFACTOR-API-02`)

### Step 4 Branches (Testing & Evaluation)
* `v0.2/refactor/test-architecture` (Covers `REFACTOR-TEST-01`, `FEAT-TEST-02`)
* `v0.2/feat/robust-eval-benchmarks` (Covers `FEAT-EVAL-01`)
* `v0.2/doc/sample-documents-enrichment` (Covers `DOC-EVAL-02`)

### Final Phase Branches (Test Coverage & Documentation)
* `v0.2/test/ingestion-and-storage` (Unit tests for new Parser Registry, Config-driven limits, and dynamic Vector Store metadata)
* `v0.2/test/retrieval-and-generation` (Unit tests for dynamic prompt assets, NLP stopwords logic, and tunable LLM configurations)
* `v0.2/test/api-and-security` (Integration/Security tests verifying strict Flask-CORS origin rules and Decoupled Pipeline factories)
* `v0.2/test/frontend-components` (Client-side DOM tests using Vitest/JSDOM verifying safe UI rendering and SSE event parsing)
* `v0.2/doc/final-coverage-and-release` (Changelog updates, test coverage reports, and v0.2.0 finalization)
