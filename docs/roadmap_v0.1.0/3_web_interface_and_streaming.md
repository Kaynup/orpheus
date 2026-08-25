# Web Interface, REST/SSE APIs & Real-Time Observability

This document provides a detailed technical breakdown of the RAG pipeline. It covers the Flask application architecture, Server-Sent Events (SSE) streaming routes, HTTP security controls, the earthy design language, safe DOM rendering, and live pipeline stage synchronization.

---

## 1. Architectural Goal & Flow

Step 3 delivers a modern, responsive web application that exposes the backend RAG pipeline through REST and streaming endpoints, synchronizing internal pipeline state transitions directly with a browser interface in real time.

```
[Browser Client (app.js)]
      │
      ├── POST /api/ingest/stream (Multipart Form) ──► SSE Event Stream
      │                                                └── Ingestion Stepper Updates
      │
      ├── POST /api/query/stream (JSON Payload)   ──► SSE Event Stream
      │                                                └── QA Stepper & Diagnostics Updates
      │
      └── POST /api/evaluate                      ──► Benchmark Report
```

---

## 2. Component-by-Component Deep Dive

### A. Flask Application Factory ([`app/main.py`](file:///home/remitpe/MAIN/rag-chat/app/main.py))

* **`create_app()` Factory Pattern**:
  * Initializes the Flask application.
  * Injects `security_headers` middleware before every request response.
  * Registers REST and SSE blueprints from `app/api/routes.py`.
  * Pre-warms the persistent ChromaDB client and embedding model on startup.
* **Strict Localhost Binding**:
  * Binds exclusively to `127.0.0.1:5000` (refusing `0.0.0.0`) to eliminate accidental exposure to external network interfaces.
  * Runs with `threaded=True` to allow concurrent SSE event streaming and document inspection requests.

---

### B. REST & Server-Sent Events (SSE) Streaming ([`app/api/routes.py`](file:///home/remitpe/MAIN/rag-chat/app/api/routes.py))

Rather than using synthetic progress bars or arbitrary timeouts, the backend uses **Server-Sent Events (`text/event-stream`)** to push actual pipeline events as they occur:

#### 1. Real-Time Query Streaming (`POST /api/query/stream`):
```python
@api_bp.route("/query/stream", methods=["POST"])
def stream_query():
    # Dispatches live events through a generator queue
    def event_stream():
        def on_event(event: PipelineEvent):
            queue.put({"event": event.to_dict()})
        
        # Runs RAG query in background worker thread
        # Yields: "data: {"event": {...}}\n\n"
        # Yields: "data: {"__FINAL_RESULT__": {...}}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")
```

#### 2. Real-Time Ingestion Streaming (`POST /api/ingest/stream`):
* Accepts uploaded files via `multipart/form-data`.
* Streams events as the document is validated, extracted, chunked, embedded, and written to ChromaDB.
* Returns final chunk count, token estimate, and page count.

#### 3. Standard REST Endpoints:
* `GET /api/status`: Returns ChromaDB collection statistics, chunk counts, and model configurations.
* `GET /api/documents`: Lists all indexed documents with page and chunk metadata.
* `DELETE /api/documents/<doc_id>`: Removes a document and its embeddings from the vector store.
* `POST /api/samples`: Automatically loads and indexes built-in sample documents.
* `POST /api/reset`: Resets the ChromaDB collection.
* `POST /api/evaluate`: Executes the benchmark suite and returns the diagnostic report.

---

### C. Security Controls & Middleware ([`app/api/security.py`](file:///home/remitpe/MAIN/rag-chat/app/api/security.py))

* **Content Security Policy (CSP)**:
  * Restricts script execution to `'self'` and `'unsafe-inline'`.
  * Restricts fonts to Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`).
  * Restricts connections to `'self'`.
* **Clickjacking Protection**: Enforces `X-Frame-Options: DENY`.
* **MIME Sniffing Protection**: Enforces `X-Content-Type-Options: nosniff`.
* **File Upload Sandboxing**:
  * Validates file size ($\le 10$ MB) and extensions (`.txt`, `.pdf`).
  * Sanitizes filenames and stores uploads in a dedicated sandboxed directory (`./data/uploads/`).

---

### D. Natural & Earthy Design System ([`app/static/css/style.css`](file:///home/remitpe/MAIN/rag-chat/app/static/css/style.css))

The user interface implements an organic, earthy visual language:

* **Color Palette**:
  * **Base Backgrounds**: Warm sand and linen (`#F7F5F0`, `#F0ECE1`, `#FAF8F5`).
  * **Primary Accents**: Forest green (`#254636`, `#1D382B`, `#E2ECE5`).
  * **Muted Accents**: Sage and moss (`#5F8571`, `#D5CBB9`).
  * **Alerts & States**: Terracotta red for errors (`#A8483B`, `#FBEAE8`), amber for warnings (`#A66E2E`, `#F9F0E0`), and soft green for success (`#1D4A2F`, `#E3EDE6`).
* **Typography**:
  * Clean modern sans-serifs (**Inter** and **Outfit**).
  * Monospaced code diagnostics (**JetBrains Mono**).
* **Calm Aesthetics**: Minimalist card borders, soft natural shadows, and clean SVG iconography.

---

### E. Frontend Logic & Safe DOM Rendering ([`app/static/js/app.js`](file:///home/remitpe/MAIN/rag-chat/app/static/js/app.js))

The frontend is written in vanilla JavaScript adhering to strict XSS prevention and reactive stream processing:

1. **Zero Raw `innerHTML` on Untrusted Data**:
   * All dynamic messages, answers, questions, and citations are rendered using native DOM APIs (`textContent`, `document.createElement`, `replaceChildren`).
2. **Real-Time Stepper Updates**:
   * Reads SSE chunks via `ReadableStream` and `TextDecoder`.
   * Maps event stages (`QUERY_RECEIVED`, `RETRIEVING_CHUNKS`, `PROMPT_PREPARED`, `GENERATING_ANSWER`) directly to the vertical stepper elements, updating CSS states (`running`, `completed`, `failed`).
3. **Interactive Inspection Drawers**:
   * **Inspect Chunks Drawer**: Opens a modal showing the exact retrieved chunks, page numbers, and cosine distance/similarity scores.
   * **Inspect Prompt Drawer**: Displays the exact prompt text and system instructions sent to the LLM.
4. **Source Citation Badges**:
   * Clickable citation pills (`[Source 1: filename]`) open a preview modal displaying the exact source snippet.
5. **Interactive Benchmark Runner**:
   * Calls `/api/evaluate` and renders pass/fail status badges, accuracy metrics, and latency diagnostics.

---

### F. Single-Page Application Layout ([`templates/index.html`](file:///home/remitpe/MAIN/rag-chat/templates/index.html))

The interface is structured into three dedicated tabs:

1. **RAG Chat & Live Pipeline Inspector**:
   * Left: Chat conversation stream, suggestion chips, model selector, top-k slider, and message area.
   * Right: Vertical process stepper showing real-time backend stage transitions and latency/token diagnostics.
2. **Document Ingestion & Knowledge Base**:
   * Left: Drag-and-drop file upload zone, chunk size/overlap controls, and vertical ingestion stepper.
   * Right: Interactive list of indexed documents with chunk and token estimates, plus individual delete buttons.
3. **Evaluation Benchmark**:
   * Summary scorecards (Pass Rate, Retrieval Accuracy, Grounding Accuracy, Refusal Accuracy, Latency).
   * Diagnostic test results table.

---

## 3. Verification & Testing

Step 3 functionality is tested via unit and integration tests in `tests/`:

* **`tests/test_api_security.py`**:
  * Verifies security headers (`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`).
  * Verifies `/api/status` endpoint structure.
  * Verifies query validation on empty inputs.
  * Verifies rejection of disallowed upload file formats (`.exe`, etc.).

---

## 4. Summary of Step 3 Deliverables

| Deliverable | Description | Location |
| :--- | :--- | :--- |
| **Flask App** | Factory pattern bound to `127.0.0.1:5000` | [`app/main.py`](file:///home/remitpe/MAIN/rag-chat/app/main.py) |
| **API Endpoints** | REST and SSE streaming routes | [`app/api/routes.py`](file:///home/remitpe/MAIN/rag-chat/app/api/routes.py) |
| **Security Headers** | CSP, clickjacking, and upload guards | [`app/api/security.py`](file:///home/remitpe/MAIN/rag-chat/app/api/security.py) |
| **HTML Template** | 3-tab single-page application layout | [`templates/index.html`](file:///home/remitpe/MAIN/rag-chat/templates/index.html) |
| **Styles** | Natural earthy stylesheet | [`app/static/css/style.css`](file:///home/remitpe/MAIN/rag-chat/app/static/css/style.css) |
| **Client JS** | SSE listener, safe DOM rendering, stepper sync | [`app/static/js/app.js`](file:///home/remitpe/MAIN/rag-chat/app/static/js/app.js) |
| **API Tests** | Security and route verification tests | [`tests/test_api_security.py`](file:///home/remitpe/MAIN/rag-chat/tests/test_api_security.py) |
