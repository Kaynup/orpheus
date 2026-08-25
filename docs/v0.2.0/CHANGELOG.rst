=============================
v0.2.0 Release Changelog
=============================

Ingestion & Storage
===========================

Added
-----
* **Parser Strategy Registry Pattern** (``app/ingestion/parser.py``):
  Introduced ``BaseDocumentParser`` abstract base class, concrete parsers (``TxtParser``, ``PdfParser``), and dictionary-based ``PARSER_REGISTRY`` with ``register_parser`` decorator to allow seamless extension for new document types without modifying core parsing routines (Open-Closed Principle).
* **Decoupled Token Estimator** (``app/chunking/tokenizer.py``):
  Created dedicated ``estimate_tokens()`` helper to isolate token counting heuristics from chunking logic, establishing an architectural seam for pluggable tokenizers (e.g., ``tiktoken``, HuggingFace).
* **Dynamic Storage & Chunking Configurations** (``app/config.py``, ``.env.example``):
  Added environment settings for:
  - ``RAG_ALLOWED_EXTENSIONS``: Configurable comma-separated file extension whitelist.
  - ``RAG_MAX_FILE_SIZE_MB``: Configurable upload file size limit.
  - ``RAG_HASH_BUFFER_SIZE``: Configurable buffer size for SHA-256 document hashing.
  - ``RAG_CHUNK_SEPARATORS``: JSON-encoded separator hierarchy for boundary-aware splitting.
  - ``CHROMA_DISTANCE_METRIC``: Configurable vector space metric (``cosine``, ``l2``, ``ip``).
  - ``CHROMA_BATCH_SIZE``: Configurable batch insertion threshold to prevent SQLite parameter overflows.

Changed / Refactored
--------------------
* **Validation Submodule Decoupling** (``app/ingestion/validator.py``):
  Removed hardcoded module-level constants (``MAX_FILE_SIZE_BYTES``, ``ALLOWED_EXTENSIONS``); file validation now dynamically defaults to ``config.storage`` while permitting explicit runtime overrides.
* **Configurable Boundary-Aware Text Splitting** (``app/chunking/text_splitter.py``):
  Refactored ``RecursiveTextSplitter`` to consume hierarchical separator lists from ``ChunkConfig`` rather than hardcoding split delimiters, and delegated token counting to ``estimate_tokens()``.
* **Embedding Model Resolution & Metric Abstractions** (``app/embedding/embedder.py``):
  Refactored ``EmbeddingManager`` to dynamically resolve embedding functions based on ``model_name``, and exposed explicit ``dimension``, ``distance_metric`` properties alongside a unified ``distance_to_similarity()`` conversion helper.
* **Metric-Agnostic Vector Storage & Safe Batching** (``app/storage/vector_store.py``):
  - Dynamic HNSW space assignment on collection initialization and reset via ``embedding_manager.distance_metric``.
  - Metric-agnostic similarity conversion in semantic query search.
  - Safe paginated insertion of document chunks in batches of ``config.storage.batch_size`` (default 1000).

Fixed
-----
* Fixed rigid file size validation and extension restrictions across document ingestion.
* Eliminated magic number (64 KB) in ``compute_file_checksum()``.
* Eliminated hardcoded cosine distance assumptions in vector retrieval scoring and distance calculation comments.


Retrieval, Generation & CLI
===========================

Added
-----
* **Versioned Prompt Asset Architecture** (``assets/prompts/``, ``app/augmentation/prompt_builder.py``):
  Extracted system instructions and user query prompt templates into independent versioned text files (``assets/prompts/system-prompts/v1_system_instruction_001.txt`` and ``assets/prompts/full-prompt-templates/v1_user_query_template_001.txt``), dynamically loaded with fail-fast validation via ``_load_asset()``.
* **Externalized NLP & Generation Config Assets** (``assets/configs/``, ``app/generation/generator.py``):
  - ``assets/configs/generation_texts.json``: Externalized standard refusal messaging, refusal detection signatures, and provider fallback note templates.
  - ``assets/configs/nlp_stopwords.json``: Externalized NLP stop words and generic domain anchor terms.
* **Centralized CLI Theme & Glyphs** (``assets/configs/cli_theme.json``, ``cli.py``):
  Externalized all CLI terminal styling tokens, status icons (``⏳``, ``⚡``, ``✔``, ``✖``), benchmark test glyphs, and prompt arrows into a centralized theme configuration.
* **Generation & Debugging Configuration Settings** (``app/config.py``, ``.env.example``):
  Added environment settings for:
  - ``LLM_DEBUG_INFO``: Toggle verbose LiteLLM telemetry and debugging info dynamically.
  - ``LLM_OFFLINE_TOPIC_THRESHOLD``: Configurable relevance ratio for offline topic matching (default 0.4).
  - ``LLM_OFFLINE_MAX_SENTENCES``: Configurable response sentence limit for offline generation (default 4).

Changed / Refactored
--------------------
* **Metric-Agnostic Retrieval Comments** (``app/retrieval/retriever.py``):
  Removed hardcoded cosine metric assumptions in proximity threshold comments.
* **Decoupled LLM Generator Orchestration** (``app/generation/generator.py``):
  Refactored ``LLMGenerator`` to dynamically consume externalized refusal strings, NLP stop words, and configurable offline thresholds.
* **Unified CLI Theme Architecture** (``cli.py``):
  Refactored event listeners, banners, tables, and interactive prompt handlers to consume tokens from the unified ``UI_THEME`` asset.

Fixed
-----
* Fixed hardcoded telemetry suppression in LiteLLM orchestration (``FIX-GEN-01``).
* Fixed hardcoded offline topic threshold and sentence length limits in fallback response generator (``FIX-GEN-04``, ``FIX-GEN-05``).
