# Step 1: Document Ingestion, Chunking & Persistent Vector Storage

This document provides a detailed breakdown of **Step 1** in the **Doc-QA Assistant** RAG pipeline. It covers document validation, text parsing with page-level provenance, boundary-aware recursive chunking, dense vector embeddings, and persistent storage in ChromaDB.

---

## 1. Architectural Goal & Pipeline Flow

The primary objective of Step 1 is to take external, unstructured business documents (`.txt` and `.pdf`) and transform them into searchable, mathematically represented vectors persisted safely on disk.

```
[Raw Files (.txt / .pdf)]
           ↓
[File Validation & Path Sanitization] (validator.py)
           ↓
[Text Extraction & Cryptographic Provenance] (parser.py)
           ↓
[Recursive Boundary-Aware Chunking] (text_splitter.py)
           ↓
[Dense Semantic Embedding Generation] (embedder.py)
           ↓
[Persistent ChromaDB Vector Store] (vector_store.py)
```

---

## 2. Component-by-Component Deep Dive

### A. Configuration & Structured Settings ([`app/config.py`](file:///home/remitpe/MAIN/rag-chat/app/config.py))

Step 1 relies on strongly-typed dataclasses for all ingestion and storage settings:

* **`ChunkConfig`**:
  * `chunk_size: int = 500` (target maximum character length per chunk).
  * `chunk_overlap: int = 50` (sliding character overlap between adjacent chunks).
  * Includes a `__post_init__` validation rule ensuring `chunk_overlap < chunk_size`.
* **`StorageConfig`**:
  * `persist_dir: str = "./data/chroma_db"` (local folder where ChromaDB stores index files and SQLite database).
  * `collection_name: str = "doc_qa_collection"` (name of the active ChromaDB vector collection).
  * `upload_dir: str = "./data/uploads"` (sandboxed directory for user uploads).
  * `samples_dir: str = "./data/sample_documents"` (directory containing pre-packaged test documents).

---

### B. Security & File Validation ([`app/ingestion/validator.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/validator.py))

Before reading or parsing any file, the system runs strict security and integrity checks:

1. **Path Traversal Protection (`sanitize_filename`)**:
   * Normalizes Windows backslashes (`\`) to forward slashes (`/`).
   * Strips path sequences (`../`, `..\`) and leading dots (`.`).
   * Whitelists safe characters (`isalnum()` plus `._- ()`).
2. **File Size Constraints**:
   * Enforces a 10 MB maximum upload limit (`MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024`).
   * Rejects empty files (0 bytes) immediately.
3. **Magic Byte / Content Inspection**:
   * **PDF Files (`.pdf`)**: Reads the initial 1024 bytes and validates that the binary header starts with `%PDF-`.
   * **Text Files (`.txt`)**: Validates that raw bytes can be cleanly decoded as UTF-8 / ASCII text without corruption.

---

### C. Document Parsing & Provenance Tracking ([`app/ingestion/parser.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/parser.py))

Once validated, the file is processed into a structured `ParsedDocument` object:

* **Cryptographic Provenance (`compute_sha256`)**:
  * Computes a SHA-256 hash of the entire file.
  * Generates a deterministic `doc_id` using UUIDv5 (`uuid.uuid5(uuid.NAMESPACE_URL, f"file://{checksum}")`).
  * Enables exact deduplication: identical documents will always generate the same `doc_id`.
* **Page-by-Page Extraction**:
  * **Plain Text (`.txt`)**: Extracts full text, counts lines and characters, and maps to `PageContent(page_number=1, ...)`.
  * **PDF Documents (`.pdf`)**: Uses `pypdf.PdfReader` to extract text page-by-page, recording individual page numbers and character counts for every discrete page.

```python
@dataclass
class PageContent:
    page_number: int
    text: str
    char_count: int

@dataclass
class ParsedDocument:
    doc_id: str
    filename: str
    file_type: str
    file_path: str
    total_chars: int
    checksum: str
    pages: List[PageContent]
    metadata: Dict[str, Any]
```

---

### D. Recursive Boundary-Aware Chunking ([`app/chunking/text_splitter.py`](file:///home/remitpe/MAIN/rag-chat/app/chunking/text_splitter.py))

Large documents cannot be fed into LLMs or vector databases as single blobs. They must be split into semantically coherent pieces while preserving exact source provenance.

#### Why Recursive Splitting?
Instead of arbitrarily slicing text at exact character counts (which cuts words or sentences in half), `RecursiveTextSplitter` uses a hierarchical priority list of natural text boundaries:
1. `\n\n` (Paragraph boundaries)
2. `\n` (Line breaks)
3. `. ` / `? ` / `! ` (Sentence endings)
4. ` ` (Word boundaries / spaces)
5. `""` (Individual characters as absolute fallback)

#### Sliding Overlap:
An overlap of 50 characters is maintained between consecutive chunks. This prevents critical context from being lost when a relevant sentence spans a chunk boundary.

#### Chunk Provenance:
Each resulting `TextChunk` retains:
* `chunk_id`: Unique identifier (e.g. `doc1_chunk_0`, `doc1_chunk_1`).
* `chunk_index`: Zero-based position index in the document.
* `content`: The raw text content of the chunk.
* `doc_id` & `source_filename`: Direct link back to the originating file.
* `page_number`: Exact page where the text appears (crucial for PDF citations).
* `start_char` & `end_char`: Character offsets within the page.
* `token_count_estimate`: Estimated token length (`len(content) // 4`).

---

### E. Semantic Embeddings ([`app/embedding/embedder.py`](file:///home/remitpe/MAIN/rag-chat/app/embedding/embedder.py))

* Uses Chroma's `DefaultEmbeddingFunction` based on the **`all-MiniLM-L6-v2`** transformer model.
* Maps textual chunks into **384-dimensional dense floating-point vector arrays**.
* Computes vector representations locally via ONNX Runtime, eliminating external API latency and cloud costs during indexing.

---

### F. Persistent Vector Storage ([`app/storage/vector_store.py`](file:///home/remitpe/MAIN/rag-chat/app/storage/vector_store.py))

* **ChromaDB Persistent Client (`chromadb.PersistentClient`)**:
  * Stores vector indexes and SQLite metadata on disk in `./data/chroma_db/`.
  * **Persistence Guarantee**: If the server restarts, vector indexes remain intact and queries run immediately without re-indexing.
* **Cosine Distance Space (`hnsw:space: "cosine"`)**:
  * Measures the cosine of the angle between query and chunk vectors.
  * Distance ranges from `0.0` (identical direction / maximum similarity) to `2.0` (opposite direction).
  * `similarity_score = 1.0 - distance`.
* **Deduplication & Clean Updates**:
  * Before inserting chunks for a `doc_id`, the store queries for existing chunks with that ID and cleans them up to avoid duplicate entries.
* **Document Management APIs**:
  * `add_chunks(chunks)`: Persists chunks and embeddings.
  * `list_documents()`: Aggregates indexed documents, total chunk counts, page counts, and estimated tokens.
  * `delete_document(doc_id)`: Removes all chunks associated with a document.
  * `reset_collection()`: Wipes the collection for a clean slate.

---

## 3. Sample Documents Catalog ([`data/sample_documents/`](file:///home/remitpe/MAIN/rag-chat/data/sample_documents/))

Step 1 includes 4 diverse, realistic sample documents to test single-document retrieval, multi-document synthesis, and anti-hallucination guardrails:

1. **`acme_hr_policy.txt`**: Acme Corp Employee Handbook (working hours 10 AM-3 PM ET, hybrid 3-day policy, $750 remote stipend, 20 PTO days, 16 weeks parental leave).
2. **`cloud_architecture_handbook.txt`**: Microservices & Resilience Manual (99.99% cloud SLA, <= 4.38 mins downtime, Redis cache-aside with 15m/1h/24h TTL, circuit breaker thresholds).
3. **`renewable_energy_faq.txt`**: Solar & Battery Guide (20-22.8% monocrystalline solar efficiency, +10-25% bifacial gain, LiFePO4 battery 6,000-8,000 cycle life at 15-35°C).
4. **`doc_qa_system_manual.txt`**: Doc-QA Architecture Specifications (384-dimensional embeddings, ChromaDB storage path, top-k retrieval parameters, anti-hallucination guardrail rules).

---

## 4. Verification & Testing

Step 1 behavior is verified through automated unit tests in `tests/`:

* **`tests/test_ingestion.py`**:
  * Tests filename sanitization and directory traversal stripping (`../../../etc/passwd` -> `passwd`).
  * Tests rejection of empty files and unsupported extensions.
  * Tests text parsing and cryptographic checksum computation.
* **`tests/test_chunking.py`**:
  * Tests recursive splitting boundaries and chunk size/overlap constraints.
  * Verifies chunk provenance fields (`doc_id`, `chunk_index`, `page_number`, `offsets`).
* **`tests/test_vector_store.py`**:
  * Tests persistent ChromaDB creation in temporary directories.
  * Verifies vector insertion, deduplication, search accuracy, and document deletion.

---

## 5. Summary of Step 1 Deliverables

| Deliverable | Description | Location |
| :--- | :--- | :--- |
| **Configuration** | Dataclasses for chunking, storage, and server | [`app/config.py`](file:///home/remitpe/MAIN/rag-chat/app/config.py) |
| **Logging** | Secret-masking structured logger | [`app/logging_config.py`](file:///home/remitpe/MAIN/rag-chat/app/logging_config.py) |
| **Validation** | File size, magic bytes, path sanitization | [`app/ingestion/validator.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/validator.py) |
| **Parsing** | `.txt` and `.pdf` parser with page metadata | [`app/ingestion/parser.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/parser.py) |
| **Chunking** | Recursive boundary text splitter with provenance | [`app/chunking/text_splitter.py`](file:///home/remitpe/MAIN/rag-chat/app/chunking/text_splitter.py) |
| **Embedding** | 384-dimensional `all-MiniLM-L6-v2` embedder | [`app/embedding/embedder.py`](file:///home/remitpe/MAIN/rag-chat/app/embedding/embedder.py) |
| **Vector Store** | Persistent ChromaDB client and manager | [`app/storage/vector_store.py`](file:///home/remitpe/MAIN/rag-chat/app/storage/vector_store.py) |
| **Sample Corpus** | 4 structured test documents | [`data/sample_documents/`](file:///home/remitpe/MAIN/rag-chat/data/sample_documents/) |
