# Understanding Python Dataclasses in Doc-QA Assistant

This document provides an educational overview of Python's `dataclasses` module (introduced in Python 3.7 and standard in Python 3.10+), explains how they work under the hood, and lists all dataclasses used throughout the **Doc-QA Assistant** codebase.

---

## 1. What is a Dataclass and How Does It Work?

A **dataclass** is a Python class decorated with `@dataclass` (from the standard library `dataclasses`). It is designed primarily to hold data and state while automatically generating standard boilerplate dunder methods behind the scenes.

### Boilerplate Automatically Generated:
When you write:
```python
from dataclasses import dataclass

@dataclass
class ChunkConfig:
    chunk_size: int = 500
    chunk_overlap: int = 50
```

Python automatically generates:
1. **`__init__(self, chunk_size=500, chunk_overlap=50)`**: Initializes fields based on type annotations and default values.
2. **`__repr__(self)`**: Provides a readable string representation (e.g., `ChunkConfig(chunk_size=500, chunk_overlap=50)`) instead of `<ChunkConfig object at 0x...>`.
3. **`__eq__(self, other)`**: Compares instances by field values rather than memory addresses.
4. **`__post_init__(self)`** (Optional): A hook executed immediately after `__init__` for validation and post-processing.
5. **`field(default_factory=...)`**: Allows mutable defaults (like lists or nested dataclass instances) without sharing state across objects.

### Key Benefits for RAG Systems:
* **Strong Typing & IDE Autocomplete**: Eliminates typos common in arbitrary dictionaries (`dict["chunk_size"]` vs `config.chunk.chunk_size`).
* **Clean Data Provenance**: Guarantees that chunks, documents, and query results retain a consistent, predictable schema throughout the pipeline.
* **Educational Readability**: Easy for developers to inspect data structures flowing between pipeline stages.

---

## 2. All Dataclasses in Doc-QA Assistant

Below is the complete catalog of dataclasses implemented in the project, organized by architectural layer.

---

### A. Configuration Layer ([`app/config.py`](file:///home/remitpe/MAIN/rag-chat/app/config.py))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`ChunkConfig`** | Settings for recursive text splitting. Validates `chunk_overlap < chunk_size` in `__post_init__`. | `chunk_size: int = 500`<br>`chunk_overlap: int = 50` |
| **`RetrievalConfig`** | Settings for semantic retrieval & relevance distance thresholding. | `top_k: int = 3`<br>`score_threshold: float = 0.90` |
| **`LLMConfig`** | Settings for LiteLLM generation and provider credentials. | `model: str`<br>`temperature: float`<br>`max_tokens: int`<br>`gemini_api_key: Optional[str]`<br>`openrouter_api_key: Optional[str]`<br>`openai_api_key: Optional[str]` |
| **`StorageConfig`** | File system paths for ChromaDB, uploads, and sample documents. | `persist_dir: str`<br>`collection_name: str`<br>`upload_dir: str`<br>`samples_dir: str` |
| **`ServerConfig`** | Host, port, and logging settings for the web backend. | `host: str = "127.0.0.1"`<br>`port: int = 5000`<br>`debug: bool`<br>`log_level: str` |
| **`AppConfig`** | Master configuration combining all sub-configurations with `.from_env()` loader. | `chunk: ChunkConfig`<br>`retrieval: RetrievalConfig`<br>`llm: LLMConfig`<br>`storage: StorageConfig`<br>`server: ServerConfig` |

---

### B. Ingestion Layer ([`app/ingestion/parser.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/parser.py))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`PageContent`** | Represents a single extracted page or section from a document. | `page_number: int`<br>`text: str`<br>`char_count: int` |
| **`ParsedDocument`** | Full parsed document representation with cryptographic SHA-256 provenance. | `doc_id: str`<br>`filename: str`<br>`file_type: str`<br>`file_path: str`<br>`total_chars: int`<br>`checksum: str`<br>`pages: List[PageContent]`<br>`metadata: Dict[str, Any]` |

---

### C. Chunking Layer ([`app/chunking/text_splitter.py`](file:///home/remitpe/MAIN/rag-chat/app/chunking/text_splitter.py))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`TextChunk`** | Discrete chunk with exact provenance (offsets, page numbers, token estimate). | `chunk_id: str`<br>`chunk_index: int`<br>`content: str`<br>`doc_id: str`<br>`source_filename: str`<br>`page_number: int`<br>`start_char: int`<br>`end_char: int`<br>`token_count_estimate: int`<br>`metadata: Dict[str, Any]` |

---

### D. Retrieval Layer ([`app/retrieval/retriever.py`](file:///home/remitpe/MAIN/rag-chat/app/retrieval/retriever.py))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`RetrievedChunk`** | Single chunk retrieved from ChromaDB with cosine distance and confidence score. | `rank: int`<br>`chunk_id: str`<br>`content: str`<br>`doc_id: str`<br>`source_filename: str`<br>`page_number: int`<br>`chunk_index: int`<br>`distance: float`<br>`similarity: float`<br>`is_confident: bool`<br>`metadata: Dict[str, Any]` |
| **`RetrievalOutput`** | Aggregated result of a semantic search operation. | `query: str`<br>`chunks: List[RetrievedChunk]`<br>`has_relevant_context: bool`<br>`top_k: int`<br>`score_threshold: float`<br>`total_indexed_chunks: int` |

---

### E. Augmentation Layer ([`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`CitationInfo`** | Metadata representing an explicit cited source for frontend badges/pills. | `source_index: int`<br>`filename: str`<br>`page_number: int`<br>`chunk_id: str`<br>`similarity: float`<br>`snippet: str` |
| **`AugmentedPrompt`** | Transparent, inspectable representation of the prompt fed to the LLM. | `system_instruction: str`<br>`formatted_context: str`<br>`user_query: str`<br>`full_prompt_text: str`<br>`citations_map: Dict[int, CitationInfo]`<br>`chunk_count: int` |

---

### F. Generation Layer ([`app/generation/generator.py`](file:///home/remitpe/MAIN/rag-chat/app/generation/generator.py))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`GenerationResult`** | Full output of the LLM generation stage including token usage and latency. | `answer: str`<br>`model: str`<br>`latency_ms: float`<br>`prompt_tokens: int`<br>`completion_tokens: int`<br>`total_tokens: int`<br>`citations: List[CitationInfo]`<br>`is_refusal: bool`<br>`is_offline_mode: bool`<br>`raw_response: Optional[Dict[str, Any]]` |

---

### G. Pipeline Orchestration & Observability ([`app/pipeline/`](file:///home/remitpe/MAIN/rag-chat/app/pipeline/))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`PipelineEvent`** (`events.py`) | Atomic backend state transition streamed via Server-Sent Events (SSE). | `stage: EventStage`<br>`status: EventStatus`<br>`message: str`<br>`data: Dict[str, Any]`<br>`timestamp: float` |
| **`IngestionResult`** (`rag_pipeline.py`) | Summary of document parsing, chunking, and vector persistence. | `doc_id: str`<br>`filename: str`<br>`file_type: str`<br>`total_chars: int`<br>`page_count: int`<br>`chunk_count: int`<br>`total_tokens_estimate: int`<br>`duration_ms: float`<br>`events: List[PipelineEvent]` |
| **`QueryResult`** (`rag_pipeline.py`) | Comprehensive summary of a question-answering query execution. | `query: str`<br>`answer: str`<br>`retrieved_chunks: List[RetrievedChunk]`<br>`citations: List[CitationInfo]`<br>`prompt: AugmentedPrompt`<br>`generation: GenerationResult`<br>`has_relevant_context: bool`<br>`is_refusal: bool`<br>`duration_ms: float`<br>`events: List[PipelineEvent]` |

---

### H. Evaluation Framework ([`app/evaluation/`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/))

| Dataclass | Purpose | Key Attributes |
| :--- | :--- | :--- |
| **`EvaluationTestCase`** (`test_dataset.py`) | Single benchmark test case with expected keywords and refusal rules. | `test_id: str`<br>`question: str`<br>`category: str`<br>`expected_keywords: List[str]`<br>`expected_source_files: List[str]`<br>`should_refuse: bool`<br>`description: str` |
| **`TestCaseResult`** (`evaluator.py`) | Diagnostic evaluation outcome of a single test case. | `test_id: str`<br>`question: str`<br>`category: str`<br>`passed: bool`<br>`retrieval_passed: bool`<br>`grounding_passed: bool`<br>`citation_passed: bool`<br>`refusal_passed: bool`<br>`is_refusal: bool`<br>`retrieved_sources: List[str]`<br>`cited_sources: List[str]`<br>`answer_preview: str`<br>`latency_ms: float`<br>`failure_reasons: List[str]` |
| **`EvaluationReport`** (`evaluator.py`) | Aggregated benchmark report with pass rates, accuracy metrics, and latency. | `total_tests: int`<br>`passed_tests: int`<br>`failed_tests: int`<br>`pass_rate_pct: float`<br>`avg_latency_ms: float`<br>`retrieval_accuracy_pct: float`<br>`grounding_accuracy_pct: float`<br>`refusal_accuracy_pct: float`<br>`results: List[TestCaseResult]`<br>`timestamp: float` |
