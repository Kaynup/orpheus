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
