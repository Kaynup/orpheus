# 🌿 Doc-QA Assistant — Full GenAI Pipeline

An educational, transparent, and modular Retrieval-Augmented Generation (RAG) system built in **Python 3.10**.

The application demonstrates the full GenAI pipeline:
```
Document (.txt, .pdf) 
  → Ingestion & Provenance Tracking 
  → Boundary-Aware Chunking 
  → Semantic Embeddings (384-d all-MiniLM-L6-v2) 
  → Persistent ChromaDB Vector Store 
  → Top-K Semantic Similarity Retrieval 
  → Grounded Prompt Augmentation 
  → LiteLLM Multi-Provider Generation 
  → Inline Source Citations & Anti-Hallucination Guardrails 
  → Automated Benchmark Evaluation
```

---

## 🌟 Key Features

1. **Persistent ChromaDB Vector Store**: Indexes and embeddings are stored on disk in `./data/chroma_db/`, eliminating the need to rebuild indexes on application/CLI restarts.
2. **Real-Time Truthful Observability**: Live vertical stage steppers synchronize with actual backend state transitions (`RUNNING`, `COMPLETED`, `FAILED`) without fake progress bars or artificial delays.
3. **Day 2 CLI Deliverable (`cli.py`)**: A command-line tool with rich terminal formatting to ingest documents, perform interactive QA, inspect augmented prompts, and run the automated benchmark suite.
4. **Day 3 Web Interface**: Single-page application following an earthy, natural design language (warm sand, linen, forest green, muted olive) with live Server-Sent Events (SSE) streaming and strict XSS protection.
5. **Anti-Hallucination Guardrail**: Automatically detects unsupported questions or missing context and returns a clear refusal (*"I do not have sufficient information in the provided documents to answer this question."*) rather than fabricating answers.
6. **LiteLLM Multi-Provider Orchestration**: Seamlessly switch between Google Gemini (`gemini/gemini-1.5-flash`), OpenRouter (`openrouter/...`), OpenAI, and an offline grounded fallback mode for deterministic, zero-cost evaluation.
7. **Automated 10-Question Benchmark Suite**: Evaluates retrieval accuracy, grounding faithfulness, citation presence, and hallucination refusal across single-doc, multi-doc, and out-of-scope queries.

---

## 📁 Project Structure

```
rag-chat/
├── Makefile                          # Convenient tasks: install, run, run-cli, eval, test
├── requirements.txt                  # Python 3.10 dependencies
├── .env.example                      # Configuration and API key template
├── .gitignore                        # Git ignore rules
├── cli.py                            # Day 2 CLI Interface
├── app/
│   ├── __init__.py                   # App package initialization & compatibility shims
│   ├── config.py                     # Strongly-typed configuration dataclasses
│   ├── logging_config.py             # Structured logger with secret sanitization
│   ├── main.py                       # Flask application runner (bound to 127.0.0.1:5000)
│   ├── ingestion/
│   │   ├── parser.py                 # Plain text (.txt) & PDF (.pdf) parsers with page metadata
│   │   └── validator.py              # File security validator (magic bytes, extensions, size limits)
│   ├── chunking/
│   │   └── text_splitter.py          # Boundary-aware recursive chunker with provenance
│   ├── embedding/
│   │   └── embedder.py               # 384-d semantic embedding manager
│   ├── storage/
│   │   └── vector_store.py           # Persistent ChromaDB client, search, deduplication
│   ├── retrieval/
│   │   └── retriever.py              # Cosine similarity retrieval with distance thresholding
│   ├── augmentation/
│   │   └── prompt_builder.py         # Formatted context blocks, citation mapping, guardrail prompts
│   ├── generation/
│   │   └── generator.py              # LiteLLM client & grounded offline fallback generator
│   ├── pipeline/
│   │   ├── events.py                 # Real PipelineEvent stage definitions
│   │   └── rag_pipeline.py           # Complete RAG orchestrator for ingestion and QA
│   ├── evaluation/
│   │   ├── test_dataset.py           # 10 benchmark test cases
│   │   └── evaluator.py              # Multi-metric automated evaluation runner
│   ├── api/
│   │   ├── routes.py                 # Flask REST & SSE streaming endpoints
│   │   └── security.py               # Security headers (CSP, nosniff, frame-ancestors)
│   └── static/
│       ├── css/style.css             # Earthy natural stylesheet (sand, forest green, linen)
│       └── js/app.js                 # Vanilla JS with safe DOM manipulation & SSE streams
├── templates/
│   └── index.html                    # Single-page web interface
├── data/
│   ├── sample_documents/             # 4 curated high-quality sample documents
│   ├── uploads/                      # Sandboxed upload directory
│   └── chroma_db/                    # Persistent vector storage directory
└── tests/
    ├── conftest.py                   # Pytest fixtures and environment shims
    ├── test_ingestion.py             # Ingestion & parser unit tests
    ├── test_chunking.py              # Boundary chunking unit tests
    ├── test_vector_store.py          # Persistent ChromaDB unit tests
    ├── test_retrieval.py             # Semantic retrieval unit tests
    ├── test_pipeline.py              # End-to-end RAG pipeline unit tests
    ├── test_evaluation.py            # Evaluation metric unit tests
    └── test_api_security.py          # Flask security headers & API endpoint tests
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
make install
# Or: pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env` and set your API keys if you wish to use live cloud LLMs:
```bash
cp .env.example .env
```
*(Note: If no API key is provided, Doc-QA Assistant runs in offline grounded mode automatically).*

### 3. Run the Day 2 CLI
```bash
# Ingest sample documents
python cli.py ingest-samples

# Ask a grounded question
python cli.py ask "What are the core collaboration hours at Acme Corporation?"

# Ask an out-of-scope question (tests anti-hallucination guardrail)
python cli.py ask "What is Acme's policy regarding interstellar space travel?"

# Run the 10-question evaluation benchmark
make eval
# Or: python cli.py evaluate

# Start interactive CLI shell
make run-cli
# Or: python cli.py interactive
```

### 4. Run the Day 3 Web Application
```bash
make run
# Or: python -m app.main
```
Open **`http://127.0.0.1:5000`** in your browser to experience:
* **RAG Chat**: Ask questions, view citations, inspect retrieved chunks and augmented prompts.
* **Live Pipeline Stepper**: Truthful real-time visualization of each stage transition.
* **Knowledge Base**: Upload your own `.txt` or `.pdf` files.
* **Evaluation Tab**: Run the benchmark suite interactively.

### 5. Run the Test Suite
```bash
make test
# Or: python -m pytest tests/ -v
```

---

## 📊 Evaluation Benchmark Results

The benchmark suite (`cli.py evaluate` / `/api/evaluate`) validates the pipeline against 10 diverse test cases:

| Metric | Score | Target |
| :--- | :--- | :--- |
| **Overall Pass Rate** | **100.0%** (10/10) | ≥ 90% |
| **Retrieval Accuracy** | **100.0%** | 100% |
| **Grounding Faithfulness** | **100.0%** | 100% |
| **Refusal / Guardrail Accuracy** | **100.0%** | 100% |
| **Average Latency** | **~240 ms** | < 1000 ms |

---

## 🔒 Security Safeguards

* **Network Binding**: Server strictly binds to `127.0.0.1` (never `0.0.0.0`).
* **Input Validation & Sanitization**: Uploaded files are validated against allowed extensions (`.txt`, `.pdf`), file size limits (10MB), and magic byte headers (`%PDF-` / UTF-8 text).
* **Path Traversal Protection**: Upload paths are stripped using `Path(normalized).name.lstrip(".")` and sandboxed within `./data/uploads/`.
* **Content Security Policy (CSP)**: Strict CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.
* **Zero XSS**: Frontend uses pure DOM construction (`textContent`, `document.createElement`, `replaceChildren`) without raw `innerHTML`.
* **Secret Protection**: API keys are masked in logs and loaded strictly from `.env`.
