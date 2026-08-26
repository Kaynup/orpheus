=============================
v0.2.0 Release Changelog
=============================

This changelog provides a comprehensive, detailed architectural record of all
features, refactorings, modularizations, security hardening, and bug fixes
introduced across the v0.2.0 development cycle (``v0.1.0`` → ``v0.1.5``).
Every entry maps directly to code changes verified in the ``git_diff_for_changelog.log``
diff produced from ``v0.1.0``…``HEAD``.


Version Bump
============

* Application version updated from ``0.1.0`` to ``0.1.5`` in ``app/version.py``
  (``__version__``, ``__version_info__``). This version string is dynamically
  surfaced by the ``/api/status`` endpoint and rendered in the frontend version
  badge (``#app-version-badge``).


----

Ingestion & Storage Subsystem
==============================

Added
-----

* **Document Parser Strategy Pattern & Extensible Registry**
  (``app/ingestion/parser.py``, ``app/ingestion/__init__.py``):

  - Introduced ``BaseDocumentParser`` abstract base class (via ``abc.ABC``)
    with a single abstract method ``parse(file_path: Path) -> ParsedDocument``.
    All format-specific parsing logic is encapsulated in concrete strategy
    subclasses, eliminating the hardcoded ``if ext == ".txt" … elif ext == ".pdf"``
    dispatch (``REFACTOR-INGEST-04``).

  - Implemented two concrete parser strategies:

    * ``TXTDocumentParser``: Reads plain text files with ``encoding="utf-8"``
      and ``errors="replace"`` fallback. Computes a deterministic ``UUID5``
      document identifier from the file's SHA-256 checksum, extracts the
      stripped full text as a single page, and records ``line_count`` and
      ``encoding`` in the document metadata dictionary.

    * ``PDFDocumentParser``: Iterates over every page via ``pypdf.PdfReader``,
      strips extracted page text, accumulates ``total_chars`` across all pages,
      rejects zero-page PDFs with a ``DocumentParsingError``, and stores
      ``page_count`` in the document metadata dictionary.

  - Established ``PARSER_REGISTRY: Dict[str, BaseDocumentParser]`` mapping
    file extensions (``".txt"``, ``".pdf"``) to singleton parser instances.
    The ``parse_document()`` dispatcher performs a registry lookup by
    extension; unknown extensions raise a descriptive ``DocumentParsingError``
    listing all registered formats. New format support (e.g. ``.md``, ``.docx``,
    ``.csv``) requires only one line: ``PARSER_REGISTRY[".new"] = NewParser()``.
    (Open-Closed Principle compliance.)

  - Maintained backward-compatible module-level wrapper functions ``parse_txt()``
    and ``parse_pdf()`` delegating to their respective registry strategies.
    Updated ``parse_document()`` to call
    ``validate_file(path, allowed_extensions=set(PARSER_REGISTRY.keys()))``
    so the allowed extension set is always in sync with registered parsers.

  - Expanded ``app/ingestion/__init__.py`` public API to export
    ``BaseDocumentParser``, ``PARSER_REGISTRY``, ``TXTDocumentParser``,
    ``PDFDocumentParser``, ``parse_txt``, and ``parse_pdf``.

* **Decoupled Token Estimation Engine**
  (``app/chunking/tokenizer.py``, ``app/chunking/__init__.py``):

  - Created ``app/chunking/tokenizer.py`` exporting ``estimate_tokens(text: str) -> int``.
  - The estimator uses the standard ``len(text) // 4`` heuristic, returning ``0``
    for empty strings and ``max(1, ...)`` for non-empty inputs (minimum 1 token).
  - Module docstring explicitly marks this as an architectural seam for future
    swap-in of ``tiktoken`` or HuggingFace tokenizers.
  - Re-exported through ``app/chunking/__init__.py`` ``__all__``.

* **Configurable Document Ingestion & Storage Settings**
  (``app/config.py``, ``.env.example``):

  ``StorageConfig`` extended:

  - ``allowed_extensions: List[str]`` — from ``RAG_ALLOWED_EXTENSIONS``
    (default ``".txt,.pdf"``).
  - ``max_file_size_bytes: int`` — from ``RAG_MAX_FILE_SIZE_MB`` (default 10 MB).
  - ``hash_buffer_size: int`` — from ``RAG_HASH_BUFFER_SIZE`` (default 65,536 bytes).
  - ``distance_metric: str`` — from ``CHROMA_DISTANCE_METRIC`` (default ``"cosine"``;
    accepts ``"l2"`` or ``"ip"``).
  - ``batch_size: int`` — from ``CHROMA_BATCH_SIZE`` (default 1000) to prevent
    SQLite variable threshold exhaustion.

  ``ChunkConfig`` extended:

  - ``separators: List[str]`` — from ``RAG_CHUNK_SEPARATORS`` as a JSON array.
    Invalid JSON falls back to the standard ``["\n\n", "\n", ". ", " ", ""]``
    sequence.

  ``LLMConfig`` extended:

  - ``suppress_debug_info: bool`` — from ``LLM_DEBUG_INFO=false``
    (default suppressed).
  - ``offline_topic_threshold: float`` — from ``LLM_OFFLINE_TOPIC_THRESHOLD``
    (default 0.4).
  - ``offline_max_sentences: int`` — from ``LLM_OFFLINE_MAX_SENTENCES``
    (default 4).

  ``ServerConfig`` extended:

  - ``cors_origins: List[str]`` — from ``CORS_ORIGINS`` (defaults to the four
    standard localhost development origins).

  All new variables fully documented in ``.env.example``.

* **Unit Test Suite for Chunking and Token Estimation**
  (``app/chunking/tests/test_chunking.py``):

  - Extended suite validating ``RecursiveTextSplitter``, custom separator
    sequences, overlap constraints, ``estimate_tokens()`` boundary conditions,
    and configurable separator injection.

Changed / Refactored
---------------------

* **Validation Submodule Decoupling & Dynamic Thresholds**
  (``app/ingestion/validator.py``):

  - Removed hardcoded module-level constants ``MAX_FILE_SIZE_BYTES`` and
    ``ALLOWED_EXTENSIONS`` (``FIX-INGEST-01``, ``REFACTOR-INGEST-02``).
  - ``validate_file()`` signature updated to
    ``validate_file(file_path, max_bytes=None, allowed_extensions=None)``.
    Both optional parameters fall back to live configuration values when not
    provided, allowing per-call override for isolated testing.
  - Error messages dynamically embed the effective byte limit and effective
    extension set.

* **Config-Driven Recursive Text Splitting**
  (``app/chunking/text_splitter.py``):

  - ``RecursiveTextSplitter.__init__()`` resolves the separator list as
    ``separators if separators is not None else config.chunk.separators``
    instead of a hardcoded Python list literal (``REFACTOR-CHUNK-01``).
  - ``token_count_estimate`` field on ``TextChunk`` now computed via
    ``estimate_tokens(piece_clean)`` (``REFACTOR-CHUNK-02``).

* **Dynamic Embedding Model Resolution & Metric Abstractions**
  (``app/embedding/embedder.py``):

  - ``EmbeddingManager`` now branches on ``model_name``; the
    ``"all-MiniLM-L6-v2"`` path instantiates ``DefaultEmbeddingFunction()``
    explicitly (``FIX-EMBED-01``).
  - Added ``dimension`` property returning vector dimension (384 for MiniLM).
  - Added ``distance_metric`` property reading from
    ``config.storage.distance_metric``.
  - Added ``distance_to_similarity(distance: float) -> float`` implementing
    metric-specific conversion:

    * Cosine / IP: ``max(0.0, 1.0 - distance)``
    * L2 (Euclidean): ``1.0 / (1.0 + distance)``
    * Unknown: cosine fallback.

* **Metric-Agnostic Vector Storage & Chunk Batching Loop**
  (``app/storage/vector_store.py``):

  - Collection initialization and ``reset_collection()`` both use
    ``metadata={"hnsw:space": self.embedding_manager.distance_metric}``
    (``FIX-STORE-01``).
  - Similarity scoring replaced with
    ``self.embedding_manager.distance_to_similarity(float(distance))``
    (``REFACTOR-STORE-02``).
  - ``add_chunks()`` persists embeddings in a paginated batch loop using
    ``config.storage.batch_size`` (``REFACTOR-STORE-03``).

Fixed
-----

* ``FIX-INGEST-01`` — File size validation no longer silently enforces a
  hardcoded 10 MB cap.
* ``FIX-INGEST-03`` — ``compute_sha256()`` reads in configurable buffer chunks;
  optional ``buffer_size`` argument also supported.
* ``FIX-STORE-01`` — ChromaDB HNSW space metadata derived dynamically from
  the embedding manager.
* ``FIX-EMBED-01`` — ``model_name`` inspection guards against silent mismatches
  between the config model name and the underlying embedding function.


----

Retrieval, Generation & CLI Subsystem
=======================================

Added
-----

* **Versioned External Prompt Asset Management**
  (``assets/prompts/``, ``app/augmentation/prompt_builder.py``):

  - Extracted system instruction into
    ``assets/prompts/system-prompts/v1_system_instruction_001.txt``
    (5-rule grounded answering contract with citation and anti-hallucination
    guardrails).
  - Extracted user query template into
    ``assets/prompts/full-prompt-templates/v1_user_query_template_001.txt``
    with ``{formatted_context}`` and ``{query}`` placeholders.
  - Added ``_load_asset(path: Path) -> str`` in ``prompt_builder.py`` with
    fail-fast ``FileNotFoundError`` including the missing path and remediation
    message.
  - ``PromptBuilder.__init__()`` loads both assets at instantiation; optional
    ``system_instruction`` constructor parameter overrides for testing.
  - Removed deprecated ``SYSTEM_INSTRUCTION`` export from
    ``app/augmentation/__init__.py``.

* **Externalized NLP & Generation Assets**
  (``assets/configs/``, ``app/generation/generator.py``):

  - ``assets/configs/generation_texts.json``:

    * ``standard_refusal`` — canonical refusal message (previously hardcoded
      at two call sites).
    * ``fallback_provider_note`` — provider fallback annotation template with
      ``{error}`` placeholder.
    * ``refusal_signatures`` — list of lowercase refusal-detection substrings.

  - ``assets/configs/nlp_stopwords.json``:

    * ``stopwords`` — ~70 common English stop words for offline topic extraction.
    * ``anchor_terms`` — generic domain words excluded from topic-word matching.

  - Added ``_load_json_asset(path: Path) -> Dict[str, Any]`` with fail-fast
    ``FileNotFoundError`` semantics.
  - Module-level constants ``DEFAULT_REFUSAL_TEXT``, ``REFUSAL_SIGNATURES``,
    ``FALLBACK_PROVIDER_NOTE_TEMPLATE``, ``STOPWORDS``, ``ANCHOR_TERMS``
    populated by parsing these JSON assets at import time.

* **Centralized CLI Theme & Glyph Tokens**
  (``assets/configs/cli_theme.json``, ``cli.py``):

  - ``assets/configs/cli_theme.json`` with two top-level keys:

    * ``icons`` — named glyph tokens: ``status_waiting`` (⏳),
      ``status_running`` (⚡), ``status_completed`` (✔), ``status_failed`` (✖),
      ``status_default`` (•), ``test_passed`` (✔), ``test_failed`` (✖),
      ``bullet`` (•), ``prompt_arrow`` (›).
    * ``colors`` — Rich console style strings per semantic role.

  - ``_load_cli_theme()`` in ``cli.py`` loads the JSON asset with a full
    in-code fallback dictionary.
  - Module-level ``UI_THEME = _load_cli_theme()`` singleton drives all
    Rich formatting calls.

* **Configurable LLM Telemetry & Offline Response Controls**
  (``app/config.py``, ``.env.example``):

  - ``LLM_DEBUG_INFO`` — controls ``litellm.suppress_debug_info`` at runtime.
  - ``LLM_OFFLINE_TOPIC_THRESHOLD`` — ratio for offline topic-word matching.
  - ``LLM_OFFLINE_MAX_SENTENCES`` — caps offline extractive sentence count.

* **Runtime Pydantic 2.13+ / LiteLLM Compatibility Shim**
  (``app/generation/generator.py``):

  - Injected ``ChatCompletionReasoningSummaryTextBlock`` stub into
    ``litellm.types.utils`` when missing, preventing ``PydanticUserError``
    on Pydantic v2 schema resolution.
  - Calls ``model_rebuild()`` on ``Message``, ``Choices``, and
    ``ModelResponse`` when available to force schema recompilation.
  - Wrapped in bare ``except Exception: pass`` to never block startup.

Changed / Refactored
---------------------

* **Decoupled Generator Orchestration**
  (``app/generation/generator.py``):

  - ``litellm.suppress_debug_info`` set per-instance from config.
  - Offline fallback threshold and sentence count read from config.
  - Hardcoded ``stopwords`` / ``anchor_terms`` replaced by JSON-loaded
    module-level constants.
  - Refusal text, fallback note, and refusal signatures reference JSON assets.

* **Metric-Agnostic Retrieval Comment Cleanup**
  (``app/retrieval/retriever.py``):

  - Replaced the misleading inline comment
    ``# e.g., cosine distance <= 0.85`` with metric-agnostic language.

* **Theme-Driven CLI Architecture**
  (``cli.py``):

  - All banners, event listeners, table borders, and benchmark icons replaced
    with ``UI_THEME["colors"]`` / ``UI_THEME["icons"]`` lookups.
  - Retrieved context table column renamed ``"Cosine Dist"`` → ``"Distance"``.
  - Interactive REPL prompt arrow uses ``UI_THEME["icons"]["prompt_arrow"]``.

Fixed
-----

* ``FIX-GEN-01`` — LiteLLM telemetry suppression is a configurable runtime
  toggle.
* ``FIX-GEN-04`` — Offline topic relevance threshold respects config.
* ``FIX-GEN-05`` — Offline sentence count cap respects config.
* ``REFACTOR-CLI-01`` — CLI theme/emoji literals centralized; missing Rich
  closing-bracket markup errors resolved across all banners.


----

Web Interface & API Subsystem
==============================

Added
-----

* **Flask-CORS Strict Localhost Whitelist Integration**
  (``app/api/security.py``, ``app/config.py``, ``app/main.py``,
  ``requirements.txt``, ``.env.example``):

  - Added ``flask-cors>=4.0.0`` to ``requirements.txt``.
  - Implemented ``setup_cors(app, allowed_origins=None)`` in
    ``app/api/security.py``. CORS scoped exclusively to ``r"/api/*"`` with
    ``supports_credentials=True``. Logs origins at ``INFO`` level; skips
    attachment with a warning when ``flask_cors`` is not installed (resilient
    import guard).
  - ``setup_cors()`` wired into ``create_app()`` immediately after
    ``setup_security_headers(app)``.
  - Default allowed origins: ``http://127.0.0.1:5000``,
    ``http://localhost:5000``, ``http://127.0.0.1:3000``,
    ``http://localhost:3000``. Overridden via ``CORS_ORIGINS`` env variable.

* **Hierarchical ES6 Frontend JavaScript Architecture**
  (``app/static/js/``):

  Deconstructed a monolithic 676-line ``app.js`` into modular ES6 components
  (``REFACTOR-UI-01``):

  - ``modules/api.js`` — Centralized REST and SSE transport client:

    * Exports: ``fetchStatus``, ``fetchDocuments``, ``deleteDocument``,
      ``loadSamples``, ``resetDatabase``, ``runEvaluation``, ``streamQuery``,
      ``streamIngest``.
    * Private ``consumeSSEStream(response, { onEvent, onFinal, onError })``:
      incrementally decodes ``ReadableStream`` bytes, splits on ``"\n\n"``
      SSE event boundaries, strips ``"data: "`` prefix, parses JSON,
      dispatches ``payload.event``, ``payload.__FINAL_RESULT__``, and
      ``payload.__ERROR__`` to caller callbacks.

  - ``modules/state.js`` — Reactive pub-sub event bus and client state:

    * Exports a shared ``state`` object (``activeFile``, ``documentCount``,
      ``version``) plus ``on(event, callback)`` and ``emit(event, data)``
      backed by a ``Map`` of listener arrays.

  - ``components/modal.js`` — Reusable modal dialog controller:

    * Exports: ``initModal()``, ``showModal(title, contentElement)``,
      ``hideModal()``. Handles close-on-backdrop-click and close-button
      binding.

  - ``components/inspector.js`` — Real-time pipeline stepper & metrics:

    * Exports: ``resetQAStepper()``, ``updateQAStep()``,
      ``resetIngestStepper()``, ``updateIngestStep()``,
      ``updateDiagnosticMetrics(res)``.
    * Stage-to-element-ID maps (``QA_STAGE_MAP``, ``INGEST_STAGE_MAP``)
      defined as module-level constants.
    * ``updateDiagnosticMetrics`` reads ``res.retrieved_chunks``,
      ``res.generation.total_tokens``, ``res.duration_ms``, and top
      chunk similarity with null-safe guards.

  - ``components/chat.js`` — Chat feed and streaming query consumer:

    * Exports: ``initChat()``.
    * Handles suggestion chip clicks, user message DOM insertion, bot
      placeholder creation, ``streamQuery`` delegation with
      ``onEvent``/``onFinal``/``onError`` callbacks, citation pill
      rendering, and ``showModal``-based chunk/prompt inspection buttons.
    * All user-controlled text inserted via ``.textContent`` (XSS-safe).

  - ``components/ingestion.js`` — Drag-and-drop upload manager:

    * Exports: ``initIngestion()``, ``updateStatus()``,
      ``loadDocumentsList()``.
    * Handles drop-zone hover/dragover/drop/click events, file selection,
      chunking config inputs, ``streamIngest`` SSE pipeline stepper updates,
      per-document card rendering with metadata, and delete confirmation.

  - ``components/evaluation.js`` — Benchmark execution and results table:

    * Exports: ``initEvaluation()``.
    * Renders loading placeholder row, calls ``runEvaluation()``, updates
      5 summary metric cards, and builds ``<tr>`` rows for each test result.

  - ``app.js`` — DOMContentLoaded bootstrap entrypoint:

    * Calls ``initTabNavigation()``, ``initModal()``, ``initChat()``,
      ``initIngestion()``, ``initEvaluation()``, ``updateStatus()``,
      ``loadDocumentsList()`` in order.
    * ``initTabNavigation()`` wires ``.nav-tab[data-target]`` attributes to
      tab panel toggling via ``classList``.

* **Modular Jinja2 Template Partials & Base Layout**
  (``templates/``):

  Deconstructed monolithic 422-line ``index.html`` into Jinja2 partials
  (``REFACTOR-UI-02``):

  - ``base.html`` — HTML5 base shell with ``{% block title %}``,
    ``{% block head %}``, ``{% block content %}``, ``{% block scripts %}``
    extension points; links Google Fonts and all CSS stylesheets.
  - ``partials/header.html`` — Navbar branding, dynamic version badge,
    ChromaDB status indicator, sample/reset action buttons, and tab bar.
  - ``partials/tab_chat.html`` — Suggestion chips, message feed area, chat
    input form, and live QA pipeline inspector stepper with diagnostic metrics.
  - ``partials/tab_ingestion.html`` — Drag-and-drop upload dropzone,
    chunk size/overlap inputs, SSE ingestion stepper, and indexed documents
    list with per-document card and delete controls.
  - ``partials/tab_evaluation.html`` — Benchmark run trigger, 5-card summary
    metrics grid, and full-width diagnostic results ``<table>`` with
    PASS/FAIL badges.
  - ``partials/modal_inspector.html`` — Fixed-position backdrop, modal card,
    title header, scrollable body, and close button.
  - ``index.html`` — Thin container extending ``base.html`` and including
    all partials.

* **Domain-Driven Component CSS Architecture**
  (``app/static/css/``):

  Decomposed monolithic 978-line ``style.css`` into domain-driven partials
  (``REFACTOR-UI-03``):

  - ``base.css`` — All CSS custom property design tokens (``:root``): earthy
    palette (warm sand, forest green, terracotta, sage accents), status state
    colors, typography scale, radius tokens, shadow definitions. Global
    box-sizing reset and body typography baseline.
  - ``layout.css`` — ``app-container``, ``app-header``, ``version-badge``,
    animated ``pulse-dot`` status indicator, ``nav-tabs``/``nav-tab`` active
    states, ``tab-pane`` toggling, full button system (``btn``,
    ``btn-primary``, ``btn-secondary``, ``btn-outline-danger``, ``btn-sm``,
    ``btn-block``, ``btn-icon``), and ``panel-card`` containers.
  - ``components/chat.css`` — ``chat-layout`` responsive CSS Grid (1fr +
    340px sidebar, collapses at 900px), message bubbles, citation pill system,
    drawer toggle buttons, chat input form.
  - ``components/inspector.css`` — Vertical stepper timeline with ``::after``
    connector lines, ``step-icon`` state classes (``running``, ``completed``,
    ``failed``), ``metric-grid`` 2-column card layout.
  - ``components/ingestion.css`` — ``drop-zone`` with dashed border and
    dragover highlight, selected file info strip, ``config-grid`` 2-column
    layout, ``doc-card`` list with type badge.
  - ``components/evaluation.css`` — ``eval-header-card``, ``eval-summary-grid``
    (auto-fit minmax), ``eval-stat-card``, ``data-table`` with sticky header,
    ``badge`` with ``badge-success`` / ``badge-fail`` variants.
  - ``components/modal.css`` — Fixed full-viewport backdrop, ``modal-card``
    with max-height scrollable body, ``modal-body pre`` with monospace and
    ``word-break``.
  - ``style.css`` — Reduced to ~12 lines of ``@import`` orchestration rules.

Changed / Refactored
---------------------

* **Decoupled Pipeline Dependency Injection**
  (``app/api/routes.py``, ``app/main.py``):

  - Removed hardcoded module-level ``rag_pipeline = RAGPipeline()`` singleton
    from ``app/api/routes.py`` (``REFACTOR-API-02``).
  - ``create_app(test_config=None, pipeline=None)`` accepts an optional
    ``pipeline: RAGPipeline | None`` argument; when ``None``, a new instance
    is created. The resolved pipeline is stored in
    ``app.extensions["rag_pipeline"]``.
  - Implemented ``get_pipeline() -> RAGPipeline`` in ``app/api/routes.py``:
    resolves from ``current_app.extensions.get("rag_pipeline")``; catches
    ``RuntimeError`` (no app context) and falls back to a module-level
    lazy singleton.
  - All 10 API route handlers now call ``get_pipeline()`` per-request.
  - In SSE streaming routes, ``pipeline = get_pipeline()`` is captured before
    spawning background threads to avoid context re-entry.

Fixed
-----

* ``REFACTOR-API-02`` — API routes no longer share a singleton pipeline at
  module import time; each test or deployment can inject a custom pipeline.
* ``REFACTOR-UI-01`` — Monolithic ``app.js`` restructured into scoped ES6
  component modules.
* ``REFACTOR-UI-02`` — Monolithic ``index.html`` split into Jinja2 partials.
* ``REFACTOR-UI-03`` — CSS refactored into seven focused domain stylesheets.


----

Security Subsystem
==================

Added
-----

* **Content-Security-Policy, Anti-Clickjacking & Anti-MIME Headers**
  (``app/api/security.py``):

  - ``setup_security_headers(app)`` registers an ``after_request`` hook
    enforcing ``Content-Security-Policy``, ``X-Frame-Options: DENY``,
    ``X-Content-Type-Options: nosniff``, and
    ``Referrer-Policy: strict-origin-when-cross-origin`` on every response.

* **CORS Strict Origin Whitelisting**
  (``app/api/security.py``):

  - ``setup_cors()`` scopes ``flask-cors`` exclusively to ``r"/api/*"``
    ensuring non-API routes (e.g. ``GET /``) never expose CORS headers to
    cross-origin callers.

* **Path Traversal Sanitization in File Upload**
  (``app/api/security.py`` → ``save_uploaded_file``):

  - ``save_uploaded_file(file, target_dir=None)`` strips all directory
    separators from client-supplied filenames via ``sanitize_filename()``
    preventing saved path from escaping the target upload directory.
  - Rejects zero-byte uploads and cleans up any partially created file.

* **Frontend DOM XSS Prevention (Static Analysis)**
  (``app/static/js/tests/test_frontend_security.py``):

  - Enforces zero-tolerance for unsafe XSS sinks:
    ``\.innerHTML\s*=``, ``document\.write(``, ``eval(``.
  - Enforces zero-tolerance for unsafe DOM injection APIs:
    ``\.insertAdjacentHTML``, ``outerHTML\s*=``.
  - Positive assertion that ``chat.js`` uses ``.textContent`` for all
    user/bot message rendering.
  - All checks scan every ``*.js`` file under ``app/static/js/``
    (excluding ``test_`` prefixed files).


----

Testing, Evaluation & Quality Assurance Subsystem
=================================================

Added
-----

* **Collocated Modular Test Architecture**
  (``app/*/tests/``, ``tests/integration/``, ``pytest.ini``, ``Makefile``):

  Transitioned from a flat ``tests/`` root layout to a high-cohesion
  collocated architecture (``REFACTOR-TEST-01``):

  - ``app/api/tests/test_api_security.py`` — 12 tests:

    * ``test_security_headers_present``: Verifies ``Content-Security-Policy``,
      ``X-Frame-Options: DENY``, ``X-Content-Type-Options: nosniff``,
      ``Referrer-Policy`` on all responses.
    * ``test_api_status_endpoint``: Status ``200``; JSON has ``status``,
      ``vector_store``, ``config`` keys.
    * ``test_api_query_empty``: Empty query → ``400`` with ``error`` key.
    * ``test_api_upload_invalid_type``: ``.py`` upload → ``400`` with
      ``"Unsupported file type"``.
    * ``test_cors_preflight_whitelisted_origin``: ``OPTIONS /api/query``
      from whitelisted origin receives ``Access-Control-Allow-Origin``
      and ``Access-Control-Allow-Credentials: true``.
    * ``test_cors_preflight_forbidden_origin``: Untrusted origin does not
      receive CORS allow headers.
    * ``test_cors_non_api_route_not_exposed``: ``GET /`` does not expose
      ``Access-Control-Allow-Origin``.
    * ``test_cors_custom_origins_configuration``: Custom ``allowed_origins``
      correctly authorizes the custom origin on OPTIONS requests.
    * ``test_create_app_with_custom_injected_pipeline``: ``create_app(pipeline=...)``
      stores the custom instance; routes resolve it on subsequent API calls.
    * ``test_save_uploaded_file_path_traversal_sanitization``: Traversal
      filename ``../../../traversal_target.txt`` sanitized to
      ``traversal_target.txt``; saved path stays inside ``tmp_path``.
    * ``test_save_uploaded_file_empty_file_rejected``: Zero-byte upload raises
      ``FileValidationError``; no file left in upload dir.
    * Flask-CORS tests carry ``@pytest.mark.skipif(CORS is None, ...)``
      guards for resilience when ``flask-cors`` is not installed.

  - ``app/chunking/tests/test_chunking.py`` — 5 tests:

    * ``test_chunking_provenance``: Single-page chunk metadata, boundaries,
      character counts, and token count estimation matching text length.
    * ``test_chunking_multipage_provenance``: Multi-page document chunking
      verifying correct page number assignment (page 1 and page 2) and
      sequential indexing across page boundaries.
    * ``test_chunking_overlap_constraint``: Raises ``ValueError`` when
      ``chunk_overlap >= chunk_size``.
    * ``test_tokenizer_estimation``: Verifies mathematical invariant
      ``estimate_tokens(s) == max(1, len(s) // 4)`` across variable string lengths.
    * ``test_configurable_separators``: Custom separator ``["||"]``; text
      ``"A||B||C"`` splits into 3 chunks with correct content.

  - ``app/embedding/tests/test_embedding.py`` — 5 tests:

    * ``test_embedding_manager_properties_consistency``: ``distance_metric``
      matches ``config.storage.distance_metric``; ``dimension`` matches
      actual embed output length.
    * ``test_distance_to_similarity_mathematical_invariants``:
      Distance 0.0 → similarity 1.0; all distances in ``[0.05…2.0]``
      produce similarities in ``[0.0, 1.0]``; monotonically non-increasing.
    * ``test_distance_to_similarity_across_supported_metrics``:
      Monkeypatches through ``"cosine"``, ``"ip"``, and ``"l2"``; asserts
      the exact formula output for each.
    * ``test_embed_documents_batch_invariance``: 3 docs → 3 vectors, each
      of length ``embedding_manager.dimension``.
    * ``test_embed_documents_empty_list``: Returns ``[]`` gracefully.

  - ``app/ingestion/tests/test_ingestion.py`` — 9 tests:

    * ``test_sanitize_filename``: Path traversal and Windows separators
      stripped to safe basename.
    * ``test_validate_nonexistent_file`` / ``test_validate_empty_file`` /
      ``test_validate_invalid_extension``: Standard validation error cases.
    * ``test_validate_dynamic_size_limit``: 200-byte file rejected at
      ``max_bytes=len(content) - 50``; accepted at
      ``max_bytes=len(content) + 50``.
    * ``test_validate_dynamic_allowed_extensions``: ``".customext"`` rejected
      when not in ``{".txt", ".pdf"}``; accepted when in ``{".customext"}``.
    * ``test_compute_sha256_buffer_invariance``: Same file produces identical
      64-char hex with default, 64-byte, and 2× config buffer sizes.
    * ``test_parse_valid_txt``: Full round-trip verifying text extraction,
      page metadata, exact cryptographic SHA-256 checksum, and deterministic
      UUID5 document ID derivation.
    * ``test_parser_registry_dynamic_extensibility``: Custom
      ``CustomDocParser`` registered in ``PARSER_REGISTRY[".customdoc"]``;
      parse verified; registration removed in ``finally``.
    * ``test_parse_unsupported_extension_error``: Unmapped extension raises
      ``FileValidationError``.

  - ``app/retrieval/tests/test_retrieval.py`` — 6 tests:

    * ``test_retrieval_matches_relevant_chunk``: Semantic search returns
      the most relevant chunk with ``is_confident=True``.
    * ``test_retrieval_empty_query``: Empty string → 0 chunks,
      ``has_relevant_context=False``.
    * ``test_retrieval_dynamic_score_threshold_override``: Very strict
      threshold marks all ``is_confident=False``; relaxed threshold marks
      all confident.
    * ``test_retrieval_dynamic_top_k_slicing``: ``top_k=1`` → 1 chunk;
      ``top_k=2`` → 2 chunks.
    * ``test_retrieval_doc_id_filter``: Filtering by doc ID returns only
      matching chunks.
    * ``test_retrieval_output_properties``: ``highest_similarity`` equals
      ``max(chunk.similarity ...)``.

  - ``app/augmentation/tests/test_prompt_builder.py`` — 6 tests:

    * ``test_prompt_builder_asset_loading``: Default ``PromptBuilder()``
      loads non-empty ``system_instruction`` and ``query_template``
      containing ``{formatted_context}`` and ``{query}`` placeholders.
    * ``test_load_asset_missing_file_raises_filenotfound``: Raises
      ``FileNotFoundError`` with ``"Prompt asset file not found"`` message.
    * ``test_prompt_builder_citation_mapping_and_indexing``: Builds prompt
      with 2 chunks; asserts 1-indexed citation map entries match source
      chunk fields and verifies source header format in
      ``formatted_context``.
    * ``test_prompt_builder_empty_chunks_fallback``: Zero chunks →
      ``formatted_context == "[NO RELEVANT CONTEXT FOUND]"``, empty
      ``citations_map``, ``chunk_count == 0``.
    * ``test_prompt_builder_custom_system_instruction_override``: Custom
      instruction overrides the file-loaded default.
    * ``test_citation_info_and_augmented_prompt_to_dict``: ``to_dict()``
      contains all expected keys; first citation has correct ``source_index``
      and ``filename``.

  - ``app/generation/tests/test_generator.py`` — 7 tests:

    * ``test_generator_telemetry_configuration``: After instantiation,
      ``litellm.suppress_debug_info`` matches ``gen.config.suppress_debug_info``.
    * ``test_load_json_asset_fail_fast``: ``_load_json_asset`` raises
      ``FileNotFoundError`` for missing path.
    * ``test_nlp_assets_loaded_successfully``: ``STOPWORDS`` and
      ``ANCHOR_TERMS`` are non-empty; common words present.
    * ``test_generator_offline_refusal_on_empty_context``: Returns
      ``DEFAULT_REFUSAL_TEXT``, ``is_refusal=True``,
      ``is_offline_mode=True``, zero citations for empty context.
    * ``test_generator_offline_refusal_on_unmatched_topics``: Unrelated
      query topic (chocolate cake) against Redis context → refusal.
    * ``test_generator_offline_extractive_grounding_and_sentence_limit``:
      Offline generator extracts relevant sentences; not a refusal;
      citations present; sentence count ≤ ``offline_max_sentences``.
    * ``test_generation_result_to_dict``: ``GenerationResult.to_dict()``
      contains all expected keys.

  - ``app/storage/tests/test_vector_store.py`` — 7 tests:

    * ``test_vector_store_add_and_search``: Inserts 2 chunks; top match
      contains ``"paid time off"``; similarity > 0.
    * ``test_vector_store_list_and_delete``: Adds 1 chunk; lists 1 doc;
      deletes it; confirms empty list.
    * ``test_vector_store_dynamic_hnsw_metadata``: Collection
      ``metadata["hnsw:space"]`` equals ``embedding_manager.distance_metric``.
    * ``test_vector_store_reset_collection_preserves_metadata``: After reset,
      count is 0; ``hnsw:space`` metadata preserved.
    * ``test_vector_store_batch_insertion_slicing``: Monkeypatches
      ``config.storage.batch_size = 2``; inserts ``batch_size + 3`` chunks;
      all persisted; count equals dynamic total.
    * ``test_vector_store_empty_add_chunks``: ``add_chunks([])`` → 0 without
      errors.
    * ``test_vector_store_similarity_delegation``: Search result
      ``similarity`` equals
      ``embedding_manager.distance_to_similarity(raw_distance)``
      (``pytest.approx``).

  - ``app/evaluation/tests/test_evaluation.py`` — 5 tests:

    * ``test_evaluator_scoring_all_dimensions``: Evaluates all 5 scoring
      dimensions on supported questions and unsupported out-of-scope refusals.
    * ``test_evaluator_max_length_constraint_failure``: Asserts that answers
      exceeding ``max_length`` fail length verification and report failure reasons.
    * ``test_evaluator_strict_keyword_grounding_failure``: Asserts that
      ``require_all_keywords=True`` strictly fails when any keyword is missing.
    * ``test_evaluator_run_benchmark_aggregate_metrics``: Runs multi-case
      benchmark suite and verifies mathematical aggregation of pass rates,
      average latency, and accuracy percentages on ``EvaluationReport``.
    * ``test_evaluator_punctuation_and_number_normalization``: Verifies
      that comma-separated numbers (``"6,000"``) and plain numbers (``"6000"``)
      match interchangeably across evaluation runs.

  - ``tests/integration/test_pipeline.py`` — 4 end-to-end integration tests:

    * ``test_pipeline_supported_query``: Strict factual recall (``"20 days"``)
      and citation provenance linking to ``vacation_policy.txt``.
    * ``test_pipeline_unsupported_query_guardrail``: Anti-hallucination refusal,
      ``is_refusal=True``, and zero citations on out-of-scope questions.
    * ``test_pipeline_event_streaming_callback``: Sequential emission of
      typed ``PipelineEvent`` records across all 7 pipeline lifecycle stages.
    * ``test_pipeline_multi_document_lifecycle_and_deletion``: Multi-document
      ingestion, cross-synthesis QA, and subsequent query refusal after
      document deletion.

  - Full automated test suite comprises **74 passing tests** across 12 test
    modules with 100% pass rate in under 15 seconds.

  - ``pytest.ini`` created with ``testpaths = app tests``, enabling
    ``pytest -v`` to discover both collocated unit tests and integration
    tests in a single run.

  - ``Makefile`` ``test`` target updated from
    ``$(PYTHON) -m pytest tests/ -v`` to ``$(PYTHON) -m pytest -v``
    (path-less invocation driven by ``pytest.ini``).


* **Automated Frontend Static Security & DOM Test Suite**
  (``app/static/js/tests/test_frontend_components.py``,
  ``app/static/js/tests/test_frontend_security.py``):

  - ``test_module_import_graph_resolution``: Dynamically scans every
    ``*.js`` file (excluding ``tests/``), extracts all relative
    ``import/export from "..."`` paths via regex, resolves each against
    the importer file's directory, asserts every resolved path exists and
    is a file, and requires at least 1 verified import.

  - ``test_state_module_exports_and_event_bus``: Reads ``modules/state.js``
    and asserts presence of ``export const state =``,
    ``export function on(``, ``export function emit(``.

  - ``test_api_transport_client_contracts``: Reads ``modules/api.js`` and
    asserts export presence of all 8 endpoint functions; also verifies
    SSE parser splits on ``"\n\n"`` boundaries and handles ``"data: "``
    prefix.

  - ``test_component_lifecycle_initializers``: For each of 5 component files
    checks all required ``export function <hook>()`` declarations are present.

  - ``test_app_bootstrap_entrypoint``: Reads ``app.js`` and asserts presence
    of all 5 init function calls and ``DOMContentLoaded`` event listener.

  - ``test_no_unsafe_sinks`` and ``test_no_unsafe_dom_apis``: Scan all
    non-test ``*.js`` files for prohibited DOM sink and API patterns;
    fail with an explicit list of violations.

  - ``test_enforces_strict_text_content``: Positive assertion that
    ``chat.js`` contains ``.textContent``.

* **Flexible & Demanding Evaluation Benchmark Logic**
  (``app/evaluation/test_dataset.py``, ``app/evaluation/evaluator.py``):

  - ``EvaluationTestCase`` extended with:

    * ``max_length: Optional[int] = None`` — model answer must be ≤ this
      many characters (excluding standard ``[Source N]`` citation tags).
    * ``require_all_keywords: bool = False`` — all expected keywords must
      be present for grounding to pass.

  - ``RAGEvaluator.evaluate_test_case()`` features:

    * **Regex Punctuation & Comma Normalization**: Evaluator applies
      ``re.sub(r'[\s\-_,]+', ' ', text)`` to match comma-separated figures
      (``"6,000"``) and unformatted numerals (``"6000"``) interchangeably.
    * **Length Boundary Constraint**: Evaluates a fifth dimension —
      **Length Constraint** — with citation stripping to prevent artificial
      failures on standard attribution formatting.

  - ``BENCHMARK_TEST_SUITE`` updated with aligned prompt instructions,
    realistic character limits (e.g. ``max_length=250``), and cross-document
    synthesis verification.

* **Real-World Sample Documents Corpus**
  (``data/sample_documents/``):

  All 4 benchmark documents substantially rewritten with dense, long-form
  realistic content:

  - ``acme_hr_policy.txt`` — Full prose HR handbook: core hours
    (10:00 AM–3:00 PM ET), mandatory in-office days (Tue/Thu), $750 home
    office stipend with 90-day receipt deadline, PTO accrual (20 days +
    10 sick), 16-week parental leave with concurrent FMLA rules.
  - ``cloud_architecture_handbook.txt`` — DevOps resiliency guide: 99.99%
    SLA definition (4.38 min/month downtime budget), Redis TTL policies
    (15-min session, 24-h static config), exponential backoff (3 retries,
    200ms base, 50% jitter), circuit breaker (50% failure rate over 60-s
    sliding window).
  - ``renewable_energy_faq.txt`` — Solar + battery technical specification:
    Mono PERC panel efficiency (20%–22.8% under STC), 25-year 85% output
    warranty, LiFePO4 cycle life (6,000–8,000 cycles at 80% DoD),
    operating temperature range (15°C–35°C).
  - ``doc_qa_system_manual.txt`` — Full RAG architectural guide: chunking
    pipeline (500-char / 50 overlap), MiniLM-L6-v2, 384-d vector space,
    ChromaDB metadata, k-NN retrieval, hallucination guardrail mechanics.

Changed / Refactored
---------------------

* **Runtime Pydantic 2.13+ LiteLLM Compatibility Shim**
  (``app/generation/generator.py``):

  - Introduced automatic schema rebuild and class injection for
    ``ChatCompletionReasoningSummaryTextBlock`` and ``Message`` to prevent
    runtime ``PydanticUserError`` during LiteLLM completions.

* **Documentation Directory Reorganization**
  (``docs/``):

  - All v0.1.0 roadmap and reference documents moved into
    ``docs/v0.1.0/`` subdirectory:

    * ``docs/dataclasses_overview.md`` → ``docs/v0.1.0/dataclasses_overview.md``
    * ``docs/evaluation_scoring_explained.md`` → ``docs/v0.1.0/evaluation_scoring_explained.md``
    * ``docs/logging_and_secrets.md`` → ``docs/v0.1.0/logging_and_secrets.md``
    * ``docs/roadmap/step1_*.md`` through ``step6_*.md`` →
      ``docs/v0.1.0/roadmap_v0.1.0/1_*.md`` through ``6_*.md``

  - v0.2.0 documents live in ``docs/v0.2.0/``:

    * ``docs/v0.2.0/CHANGELOG.rst`` (this file)
    * ``docs/v0.2.0/fixes-and-changes.md`` — full architecture review
      backlog with tagged items, priority rankings, and branch strategy.
    * ``docs/v0.2.0/core_functionalities/`` — comprehensive 8-module
      technical documentation suite mapping BRD requirements (FR1–FR8,
      NFR1–NFR5) with bidirectional Mermaid flow, sequence, state, and
      architecture diagrams.


Fixed
-----

* ``REFACTOR-TEST-01`` — Tests are now collocated with source; root
  ``tests/`` retains only integration tests.
* ``DOC-EVAL-02`` — Sample document corpus enriched with dense realistic
  content substantially increasing retrieval challenge difficulty.
* **CLI Theme Formatting Syntax** (``cli.py``):
  Resolved missing closing brackets in Rich console markup style tags
  across ingestion banners, headers, and question inspectors.

