=============================
v0.2.0 Release Changelog
=============================

This changelog provides a comprehensive, detailed architectural record of all features, refactorings, modularizations, and bug fixes introduced across the v0.2.0 development cycle.


Ingestion & Storage Subsystem
=============================

Added
-----
* **Document Parser Strategy Pattern & Extensible Registry** (``app/ingestion/parser.py``, ``app/ingestion/__init__.py``):
  - Abstracted document parsing behind ``BaseDocumentParser`` with an abstract ``parse(file_path: Path) -> ParsedDocument`` interface.
  - Implemented concrete parser strategies:
    * ``TXTDocumentParser``: Plain text reader with UTF-8 encoding fallback and deterministic UUID5 identification based on file checksum.
    * ``PDFDocumentParser``: Multi-page PDF extraction engine with per-page text aggregation and character counting using ``pypdf``.
  - Established a centralized ``PARSER_REGISTRY`` dictionary mapping file extensions (``.txt``, ``.pdf``) to parser strategy instances. New document format parsers can be registered dynamically without modifying core parsing dispatch logic (Open-Closed Principle).
  - Maintained backward-compatible wrapper functions ``parse_txt()``, ``parse_pdf()``, and ``parse_document()``.
* **Decoupled Token Estimation Engine** (``app/chunking/tokenizer.py``, ``app/chunking/__init__.py``):
  - Created a dedicated ``estimate_tokens(text: str) -> int`` utility, isolating token estimation heuristics (character count heuristics with minimum non-empty bounds) from chunk splitting logic.
  - Formed a clean architectural seam enabling future pluggable tokenizers (such as ``tiktoken`` or HuggingFace tokenizers).
* **Configurable Document Ingestion & Storage Settings** (``app/config.py``, ``.env.example``):
  - ``RAG_ALLOWED_EXTENSIONS``: Configurable comma-separated list of permitted file extensions (defaults to ``.txt,.pdf``).
  - ``RAG_MAX_FILE_SIZE_MB``: Configurable maximum document upload size in megabytes (defaults to 10 MB, stored as ``max_file_size_bytes``).
  - ``RAG_HASH_BUFFER_SIZE``: Configurable read buffer size for streaming SHA-256 file checksum calculation (defaults to 65,536 bytes).
  - ``RAG_CHUNK_SEPARATORS``: JSON-encoded array specifying the hierarchical separator fallback sequence for recursive text chunking.
  - ``CHROMA_DISTANCE_METRIC``: Configurable vector space metric (``cosine``, ``l2``, ``ip``) matching collection geometry.
  - ``CHROMA_BATCH_SIZE``: Configurable chunk insertion batch limit (defaults to 1000) to prevent SQLite parameter threshold exhaustion.
* **Unit Test Suite for Chunking and Token Estimation** (``tests/test_chunking.py``):
  - Comprehensive unit test suite validating ``RecursiveTextSplitter``, custom separator sequences, overlap constraints, and ``estimate_tokens()`` behavior.

Changed / Refactored
--------------------
* **Validation Submodule Decoupling & Dynamic Thresholds** (``app/ingestion/validator.py``):
  - Eliminated hardcoded module-level constants (``MAX_FILE_SIZE_BYTES``, ``ALLOWED_EXTENSIONS``).
  - Refactored ``validate_file()`` to dynamically resolve limits from ``config.storage.max_file_size_bytes`` and ``config.storage.allowed_extensions`` while supporting explicit per-call argument overrides.
* **Config-Driven Recursive Text Splitting** (``app/chunking/text_splitter.py``):
  - Refactored ``RecursiveTextSplitter`` to consume hierarchical separator lists from ``ChunkConfig.separators`` instead of hardcoded strings.
  - Integrated ``estimate_tokens()`` for chunk-level token estimates.
* **Dynamic Embedding Model Resolution & Metric Abstractions** (``app/embedding/embedder.py``):
  - Enhanced ``EmbeddingManager`` to dynamically resolve embedding functions based on ``model_name``.
  - Exposed explicit model properties: ``dimension`` (vector dimension, default 384) and ``distance_metric`` (resolved from storage configuration).
  - Added unified ``distance_to_similarity(distance: float) -> float`` conversion helper mapping raw distance to normalized ``[0.0, 1.0]`` similarity across Cosine, Inner Product (IP), and Euclidean (L2) spaces.
* **Metric-Agnostic Vector Storage & Chunk Batching Loop** (``app/storage/vector_store.py``):
  - Configured ChromaDB collections with dynamic HNSW space metadata (``metadata={"hnsw:space": self.embedding_manager.distance_metric}``) on initialization and collection reset.
  - Replaced hardcoded cosine similarity math with ``self.embedding_manager.distance_to_similarity(dist)`` in query result formatting.
  - Implemented safe paginated batch insertion in ``add_chunks()`` looping over chunks in increments of ``config.storage.batch_size`` (default 1000) with detailed logging.

Fixed
-----
* Eliminated rigid file size validation and extension restrictions across document ingestion routines.
* Removed hardcoded 64 KB magic number in ``compute_sha256()``, replacing it with configurable buffer sizing.
* Fixed hardcoded cosine distance assumptions in vector retrieval scoring.


Retrieval, Generation & CLI Subsystem
=====================================

Added
-----
* **Versioned External Prompt Asset Management** (``assets/prompts/``, ``app/augmentation/prompt_builder.py``):
  - Extracted hardcoded system instructions into ``assets/prompts/system-prompts/v1_system_instruction_001.txt``.
  - Extracted user query template into ``assets/prompts/full-prompt-templates/v1_user_query_template_001.txt``.
  - Implemented ``_load_asset()`` in ``PromptBuilder`` with fail-fast file validation, while maintaining optional constructor parameter overrides for testing.
  - Cleaned up ``app/augmentation/__init__.py`` to remove deprecated prompt string exports.
* **Externalized NLP & Generation Assets** (``assets/configs/``, ``app/generation/generator.py``):
  - ``assets/configs/generation_texts.json``: Externalized standard refusal response message, refusal detection signatures, and provider fallback note templates.
  - ``assets/configs/nlp_stopwords.json``: Externalized NLP stop words and generic domain anchor terms used for topic keyword filtering.
  - Implemented robust ``_load_json_asset()`` loader with fail-fast validation.
* **Centralized CLI Theme & Glyph Tokens** (``assets/configs/cli_theme.json``, ``cli.py``):
  - Centralized terminal styling tokens, status icons (``⏳``, ``⚡``, ``✔``, ``✖``, ``•``, ``›``), table border styles, and alert colors in ``assets/configs/cli_theme.json``.
  - Implemented resilient fallback loader ``_load_cli_theme()`` in ``cli.py``.
* **Configurable LLM Telemetry & Offline Response Controls** (``app/config.py``, ``.env.example``):
  - ``LLM_DEBUG_INFO``: Boolean environment variable to toggle verbose LiteLLM telemetry and debugging info dynamically.
  - ``LLM_OFFLINE_TOPIC_THRESHOLD``: Configurable relevance ratio for offline topic matching (defaults to 0.4).
  - ``LLM_OFFLINE_MAX_SENTENCES``: Configurable response sentence limit for offline generation (defaults to 4).

Changed / Refactored
--------------------
* **Metric-Agnostic Retrieval Documentation** (``app/retrieval/retriever.py``):
  - Removed hardcoded metric assumptions in semantic proximity threshold comments.
* **Decoupled Generator Orchestration** (``app/generation/generator.py``):
  - Configured ``litellm.suppress_debug_info`` dynamically from ``config.llm.suppress_debug_info``.
  - Refactored offline fallback extraction to consume externalized stop words, anchor terms, configurable topic thresholds, and configurable sentence limits.
* **Theme-Driven CLI Architecture** (``cli.py``):
  - Refactored all banners, event listeners, summaries, question inspectors, and benchmark tables to render using ``UI_THEME`` tokens.

Fixed
-----
* Fixed hardcoded telemetry suppression in LiteLLM orchestration (``FIX-GEN-01``).
* Fixed hardcoded offline topic threshold and sentence length limits in fallback response generator (``FIX-GEN-04``, ``FIX-GEN-05``).


Web Interface & API Subsystem
=============================

Added
-----
* **Flask-CORS Strict Localhost Whitelist Integration** (``app/api/security.py``, ``app/config.py``, ``requirements.txt``, ``.env.example``):
  - Added ``flask-cors>=4.0.0`` dependency.
  - Added ``cors_origins`` configuration to ``ServerConfig`` parsed from ``CORS_ORIGINS`` environment variable (defaults to ``http://127.0.0.1:5000``, ``http://localhost:5000``, ``http://127.0.0.1:3000``, ``http://localhost:3000``).
  - Implemented ``setup_cors(app)`` scoping strict origins on ``r"/api/*"`` routes with ``supports_credentials=True``.
  - Connected CORS middleware in ``create_app()`` in ``app/main.py``.
* **Hierarchical ES6 Frontend JavaScript Architecture** (``app/static/js/``):
  - Deconstructed monolithic 676-line ``app.js`` into modular ES6 modules and components:
    * ``modules/api.js``: Centralized transport client for REST endpoints and Server-Sent Events (SSE) streaming readers (``streamQuery``, ``streamIngest``, ``fetchStatus``, ``fetchDocuments``, ``deleteDocument``, ``loadSamples``, ``resetDatabase``, ``runEvaluation``).
    * ``modules/state.js``: Reactive pub-sub event bus and client state manager (``state``, ``on``, ``emit``).
    * ``components/modal.js``: Reusable modal dialog controller for prompt and context chunk inspection.
    * ``components/inspector.js``: Real-time pipeline vertical steppers (running, completed, failed states) and diagnostic metrics panel.
    * ``components/chat.js``: Chat feed manager, streaming response consumer, suggestion chips, and source citation pill renderer.
    * ``components/ingestion.js``: Drag-and-drop file upload, chunking configuration inputs, indexed document card list, and sample loader.
    * ``components/evaluation.js``: Benchmark execution trigger, summary metrics card updates, and diagnostic results table renderer.
    * ``app.js``: Clean application bootstrap entrypoint and tab navigation router.
* **Modular Jinja2 Template Partials & Base Layout** (``templates/``):
  - Deconstructed monolithic 422-line ``index.html`` into structured Jinja2 partials:
    * ``base.html``: Clean HTML5 base shell with typography, stylesheets, and Jinja2 blocks (``title``, ``head``, ``content``, ``scripts``).
    * ``partials/header.html``: Navbar branding, dynamic version badge, status indicator, sample/reset actions, and navigation tabs.
    * ``partials/tab_chat.html``: Chat interface, suggestion chips, message feed, and live QA pipeline inspector.
    * ``partials/tab_ingestion.html``: Ingestion upload zone, parameter inputs, stepper, and indexed document list.
    * ``partials/tab_evaluation.html``: Benchmark execution header, 5-metric summary grid, and diagnostic results table.
    * ``partials/modal_inspector.html``: Reusable inspector details modal dialog.
    * ``index.html``: Container template extending ``base.html`` and including partials.
* **Domain-Driven Component CSS Architecture** (``app/static/css/``):
  - Decomposed monolithic 978-line ``style.css`` into focused, domain-driven stylesheets imported via ``style.css``:
    * ``base.css``: Earthy color palette tokens (``:root``), CSS reset, and typography.
    * ``layout.css``: App container, header branding, navigation tabs, panels, and button utilities.
    * ``components/chat.css``: Chat layout, message bubbles, citation pills, and input controls.
    * ``components/inspector.css``: Stepper timeline, running/completed/failed states, and diagnostic metrics grid.
    * ``components/ingestion.css``: Drag-and-drop dropzone, upload info, and document cards.
    * ``components/evaluation.css``: Benchmark cards, diagnostic results table, and pass/fail badges.
    * ``components/modal.css``: Modal backdrop and dialog cards.
    * ``style.css``: Master stylesheet orchestrating modular ``@import`` rules.

Changed / Refactored
--------------------
* **Decoupled Pipeline Dependency Injection** (``app/api/routes.py``, ``app/main.py``):
  - Removed hardcoded module-level ``rag_pipeline = RAGPipeline()`` singleton from API routes.
  - Injected pipeline instance via Flask application context (``app.extensions["rag_pipeline"]``) in ``create_app()``.
  - Implemented thread-safe ``get_pipeline() -> RAGPipeline`` accessor resolving from ``current_app.extensions`` with lazy fallback.
  - Captured pipeline instances in request contexts prior to spawning streaming worker threads in SSE endpoints.

Fixed
-----
* Eliminated tight coupling of API routes to a singleton pipeline instance (``REFACTOR-API-02``).
* Fixed monolithic frontend architecture by deconstructing JS, Jinja2 templates, and CSS into domain-driven modular files (``REFACTOR-UI-01``, ``REFACTOR-UI-02``, ``REFACTOR-UI-03``).


Testing, Evaluation & Quality Assurance Subsystem
=================================================

Added
-----
* **Collocated Modular Test Architecture** (``app/*/tests/``, ``tests/integration/``, ``pytest.ini``, ``Makefile``):
  - Transitioned the entire test suite from a centralized root layout to a high-cohesion, collocated architecture within each source package:
    * ``app/api/tests/test_api_security.py``: Strict Flask-CORS origin preflight verification, untrusted origin rejection, non-API route isolation, custom allowed origins configuration, decoupled pipeline factory injection (``create_app(pipeline=...)``), and path traversal sanitization in file uploads.
    * ``app/chunking/tests/test_chunking.py``: Recursive text splitting, custom separator fallback, overlap boundaries, and token estimation tests.
    * ``app/embedding/tests/test_embedding.py``: Dynamic dimension and metric consistency, mathematical boundary and monotonicity contracts for ``distance_to_similarity`` across Cosine, L2, and IP spaces, and batch shape invariance.
    * ``app/ingestion/tests/test_ingestion.py``: Dynamic Parser Strategy Registry extensibility (OCP), unmapped extension error handling, SHA-256 buffer invariance, and config-driven ``validate_file`` size/extension limits.
    * ``app/retrieval/tests/test_retrieval.py``: Metric-agnostic score threshold filtering, dynamic ``top_k`` boundary slicing, document ID filtering, and summary property metrics.
    * ``app/augmentation/tests/test_prompt_builder.py``: Dynamic prompt asset loading from ``assets/prompts/``, fail-fast missing asset validation, 1-indexed citation mapping, and empty context fallback handling.
    * ``app/generation/tests/test_generator.py``: Dynamic LiteLLM telemetry toggle, fail-fast JSON asset loader, offline grounded extractive fallback, dynamic topic threshold matching, and sentence limit boundaries.
    * ``app/storage/tests/test_vector_store.py``: Dynamic HNSW space metadata (``hnsw:space``), batch insertion slicing over ``batch_size`` increments, collection reset metadata preservation, and similarity delegation.
    * ``app/evaluation/tests/test_evaluation.py``: Automated scoring, retrieval verification, factual keyword grounding, and refusal guardrail assertions.
  - Retained end-to-end multi-stage pipeline lifecycle tests in ``tests/integration/test_pipeline.py``.
  - Configured ``pytest.ini`` with unified discovery paths (``testpaths = app tests``) and clean root configuration.
  - Updated ``Makefile`` test target to execute ``python3 -m pytest -v`` across all collocated and integration suites.
* **Automated Frontend Static Security & DOM Test Suite** (``app/static/js/tests/test_frontend_security.py``, ``app/static/js/tests/test_frontend_components.py``):
  - Built an automated AST/source-scanning unit and security test suite validating all client-side JavaScript components (``app/static/js/**/*.js``).
  - Enforces zero-tolerance policy for unsafe XSS sinks (``innerHTML``, ``outerHTML``, ``document.write``).
  - Validates exclusive usage of safe DOM APIs (``textContent``, ``innerText``, ``createElement``, ``setAttribute``).
  - Guards against dangerous runtime code evaluation patterns (``eval()``, ``Function()`` constructor, string-based ``setTimeout``).
  - Validates 100% resolution of ES6 module import dependency graphs, state pub-sub event bus methods (``on``, ``emit``), REST transport endpoints, SSE stream boundary parsing, and component lifecycle hooks (``initChat``, ``initIngestion``, ``initEvaluation``, ``initInspector``).
* **Demanding Evaluation Benchmark & Constraint Logic** (``app/evaluation/test_dataset.py``, ``app/evaluation/evaluator.py``):
  - Extended ``EvaluationTestCase`` dataclass with strict constraint parameters:
    * ``max_length: Optional[int]``: Enforces character-length boundaries on model outputs.
    * ``require_all_keywords: bool``: Requires 100% keyword recall for demanding multi-document synthesis queries.
  - Upgraded ``BENCHMARK_TEST_SUITE`` queries with tighter topic thresholds, concise character bounds (e.g. <100 chars), and multi-document synthesis assertions.
  - Embedded length boundary verification and all-keyword grounding assertions into ``RAGEvaluator.evaluate_test_case()``.
* **Real-World Sample Documents Corpus** (``data/sample_documents/``):
  - Enriched and expanded all 4 core benchmark files with dense, realistic policies, specifications, and architecture guides:
    * ``acme_hr_policy.txt``: Comprehensive Employee Handbook with detailed hybrid work rules, core hours, stipend eligibility, and parental leave policies.
    * ``cloud_architecture_handbook.txt``: In-depth DevOps resilient systems handbook detailing 99.99% SLAs, Redis caching TTLs, exponential backoff, and circuit breaker patterns.
    * ``renewable_energy_faq.txt``: Technical specification and FAQ covering Mono PERC solar panel efficiency, LiFePO4 battery chemistry, and thermal limits.
    * ``doc_qa_system_manual.txt``: Full RAG architectural guide detailing ingestion pipelines, MiniLM 384-d embeddings, and ChromaDB vector store mechanics.

Changed / Refactored
--------------------
* **Runtime Pydantic 2.13+ LiteLLM Compatibility Shim** (``app/generation/generator.py``):
  - Introduced automatic schema rebuild and class injection for ``ChatCompletionReasoningSummaryTextBlock`` and ``Message`` to prevent runtime PydanticUserError during LiteLLM completions.

Fixed
-----
* **CLI Theme Formatting Syntax** (``cli.py``):
  - Resolved missing closing brackets in Rich console markup style tags across ingestion banners, headers, and question inspectors.

