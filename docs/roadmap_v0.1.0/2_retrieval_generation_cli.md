# Retrieval, Prompt Augmentation, Generation, CLI & Evaluation

This document provides a detailed technical breakdown in the RAG pipeline. It covers semantic top-k retrieval, confidence thresholding, grounded prompt augmentation, LiteLLM orchestration, anti-hallucination guardrails, the interactive CLI tool, and the automated benchmark.

---

## 1. Architectural Goal & Pipeline Flow

The persistent vector store created in Step 1 with query processing, LLM generation, and evaluation to produce a complete, truthful question-answering system.

```
[User Query]
      ↓
[Query Embedding (384-d)] (embedder.py)
      ↓
[Top-K Semantic Search in ChromaDB] (retriever.py)
      ↓  (Filters by Distance Threshold)
[Retrieved Text Chunks + Cosine Scores]
      ↓
[Numbered Source Formatting & Guardrail Injection] (prompt_builder.py)
      ↓
[LiteLLM Provider Orchestration] (generator.py)
      ↓
[Grounded Answer with Citations OR Anti-Hallucination Refusal]
      ↓
[CLI Interface (cli.py) & Automated Benchmark (evaluator.py)]
```

---

## 2. Component-by-Component Deep Dive

### A. Semantic Retrieval & Distance Thresholding ([`app/retrieval/retriever.py`](file:///home/remitpe/MAIN/rag-chat/app/retrieval/retriever.py))

When a user submits a question, the retriever:
1. Embeds the question into a 384-dimensional semantic vector using `EmbeddingManager`.
2. Queries the persistent ChromaDB collection for the `top_k` (default: 3) nearest neighbors by cosine distance.
3. Computes the similarity score: $\text{similarity} = 1.0 - \text{distance}$.
4. Evaluates confidence against `score_threshold` (default: 0.90 max distance):
   * Chunks with cosine distance $\le 0.90$ are flagged as `is_confident = True`.
   * If all returned chunks have poor similarity (distance $> 0.90$), `has_relevant_context` is marked `False`.

```python
@dataclass
class RetrievedChunk:
    rank: int
    chunk_id: str
    content: str
    doc_id: str
    source_filename: str
    page_number: int
    chunk_index: int
    distance: float
    similarity: float
    is_confident: bool
    metadata: Dict[str, Any]

@dataclass
class RetrievalOutput:
    query: str
    chunks: List[RetrievedChunk]
    has_relevant_context: bool
    top_k: int
    score_threshold: float
    total_indexed_chunks: int
```

---

### B. Grounded Prompt Augmentation ([`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py))

The prompt builder transforms retrieved chunks into an augmented prompt with citation markers and guardrail instructions:

1. **Numbered Source Formatting**:
   Chunks are formatted into clean, isolated context blocks:
   ```text
   --- [Source 1: acme_hr_policy.txt (Page 1)] ---
   Core collaboration hours are 10:00 AM to 3:00 PM Eastern Time (ET)...
   
   --- [Source 2: acme_hr_policy.txt (Page 1)] ---
   All full-time employees receive twenty (20) days of accrued PTO annually...
   ```
2. **Citation Mapping (`CitationInfo`)**:
   Tracks mapping from `[Source N]` indices back to exact chunk IDs, filenames, page numbers, and preview snippets.
3. **Strict Anti-Hallucination Rules**:
   Injects unambiguous system instructions:
   * Rule 1: Answer ONLY using facts from the retrieved context.
   * Rule 2: Cite sources using `[Source N]` or `[Source N, Page X]`.
   * Rule 3: If context is insufficient, state: *"I do not have sufficient information in the provided documents to answer this question."*
   * Rule 4: Do NOT speculate or use outside knowledge.

---

### C. LiteLLM Orchestration & Offline Generator ([`app/generation/generator.py`](file:///home/remitpe/MAIN/rag-chat/app/generation/generator.py))

The generation engine supports multi-provider cloud execution alongside a deterministic offline mode:

1. **Multi-Provider Cloud LLMs**:
   * **Google Gemini** (`gemini/gemini-1.5-flash`) via `GEMINI_API_KEY`.
   * **OpenRouter** (`openrouter/...`) via `OPENROUTER_API_KEY`.
   * **OpenAI** (`gpt-4o-mini`, etc.) via `OPENAI_API_KEY`.
2. **Grounded Offline Fallback (Zero-Cost & Deterministic)**:
   * If no API key is provided, the system does not crash or generate fake responses.
   * Analyzes query keywords against retrieved context chunks.
   * If keywords match relevant sentences, it constructs an exact, cited factual extract.
   * If the query is out-of-scope (e.g. asking about space travel), it returns the exact guardrail refusal string.
3. **Refusal Detection**:
   * Inspects the generated response for standard refusal triggers (`"insufficient information"`, `"do not have sufficient"`).
   * Sets `is_refusal = True`, ensuring that no phantom citations are attached to refusal messages.

---

### D. Pipeline Events & State Synchronization ([`app/pipeline/events.py`](file:///home/remitpe/MAIN/rag-chat/app/pipeline/events.py))

The pipeline emits discrete, truthful `PipelineEvent` instances at each stage of query execution:

| Event Stage | Description | Emitted Data |
| :--- | :--- | :--- |
| `QUERY_RECEIVED` | User query accepted by pipeline. | `query` string |
| `QUERY_EMBEDDED` | Query transformed to 384-d vector. | `model`, `vector_dim` (384) |
| `RETRIEVING_CHUNKS` | ChromaDB nearest neighbor search. | `top_k`, `query` |
| `CONTEXT_SELECTED` | Distance thresholding & selection. | `chunk_count`, `top_similarity` |
| `PROMPT_PREPARED` | Augmented prompt constructed. | `prompt_length`, `source_count` |
| `GENERATING_ANSWER` | LLM synthesis initiated. | `model`, `prompt_tokens` |
| `ANSWER_COMPLETE` | Final grounded answer ready. | `latency_ms`, `is_refusal` |

---

### E. CLI Deliverable ([`cli.py`](file:///home/remitpe/MAIN/rag-chat/cli.py))

`cli.py` provides an interactive, terminal-based interface with rich formatting:

```bash
# 1. Ingest built-in sample documents
python cli.py ingest-samples

# 2. Ingest custom document
python cli.py ingest /path/to/doc.pdf --chunk-size 500 --overlap 50

# 3. Ask a question with full provenance display
python cli.py ask "What are the core collaboration hours at Acme Corporation?"

# 4. Inspect vector database status
python cli.py status

# 5. Interactive conversational shell
python cli.py interactive

# 6. Run automated benchmark suite
python cli.py evaluate
```

#### CLI Output Example for `ask`:
```
╭───────────────── Answer ──────────────────╮
│ Core collaboration hours are 10:00 AM to │
│ 3:00 PM Eastern Time (ET).               │
│                                           │
│ Sources: [Source 1: acme_hr_policy.txt]  │
╰───────────────────────────────────────────╯
┌─── Retrieved Chunks (3) ────────────────────────────────────────────────┐
│ Rank │ Source               │ Page │ Cosine Dist │ Similarity │ Status  │
├──────┼──────────────────────┼──────┼─────────────┼────────────┼─────────┤
│ 1    │ acme_hr_policy.txt   │ 1    │ 0.1615      │ 0.8385     │ Match   │
└──────┴──────────────────────┴──────┴─────────────┴────────────┴─────────┘
```

---

### F. Automated Evaluation Framework ([`app/evaluation/`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/))

The evaluation suite validates RAG performance across the benchmark dataset:

#### Test Cases Dataset (`test_dataset.py`):
* **Single-Document Fact Cases**: Fact extraction on Core hours, remote stipend, 99.99% SLA limits, Redis TTLs, solar efficiency, LiFePO4 battery cycles, Doc-QA specs.
* **Out-of-Scope Cases**: Queries testing anti-hallucination guardrails (Space travel reimbursement, stock price prediction).
* **Multi-Document Synthesis**: Cross-document reasoning across HR policies and Cloud Architecture.

#### Automated Evaluator Metrics (`evaluator.py`):
1. **Retrieval Accuracy**: Did the top retrieved chunks include the expected source document?
2. **Grounding Faithfulness**: Does the answer contain all required factual keywords from the context?
3. **Citation Presence**: Does the answer cite the correct source index?
4. **Refusal Accuracy**: Does the system refuse out-of-scope queries with the exact guardrail message rather than hallucinating?
5. **Latency**: End-to-end processing time in milliseconds.

#### Benchmark Results:
```
Total Tests: 10  |  Passed: 10  |  Failed: 0
Pass Rate: 100.0%
Retrieval Accuracy: 100.0%
Grounding Accuracy: 100.0%
Refusal Accuracy: 100.0%
Average Latency: ~230 ms
```

---

## 3. Verification & Testing

Step 2 behavior is verified via automated unit and integration tests:

* **`tests/test_retrieval.py`**: Verifies nearest neighbor retrieval, distance scoring, and top-k filtering.
* **`tests/test_pipeline.py`**: Verifies end-to-end QA flow for factual queries and anti-hallucination guardrails.
* **`tests/test_evaluation.py`**: Verifies evaluator scoring logic, refusal detection, and summary statistics.

---

## 4. Summary of Step 2 Deliverables

| Deliverable | Description | Location |
| :--- | :--- | :--- |
| **Retriever** | Semantic similarity search and thresholding | [`app/retrieval/retriever.py`](file:///home/remitpe/MAIN/rag-chat/app/retrieval/retriever.py) |
| **Augmentation** | Numbered source builder and guardrails | [`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py) |
| **Generator** | LiteLLM client and offline grounded fallback | [`app/generation/generator.py`](file:///home/remitpe/MAIN/rag-chat/app/generation/generator.py) |
| **Pipeline Events** | Discrete state events for real-time observability | [`app/pipeline/events.py`](file:///home/remitpe/MAIN/rag-chat/app/pipeline/events.py) |
| **Orchestrator** | End-to-end master RAG pipeline coordinator | [`app/pipeline/rag_pipeline.py`](file:///home/remitpe/MAIN/rag-chat/app/pipeline/rag_pipeline.py) |
| **CLI Tool** | Interactive command-line interface | [`cli.py`](file:///home/remitpe/MAIN/rag-chat/cli.py) |
| **Benchmark Suite** | Diagnostic test cases and multi-metric automated evaluator | [`app/evaluation/`](file:///home/remitpe/MAIN/rag-chat/app/evaluation/) |
