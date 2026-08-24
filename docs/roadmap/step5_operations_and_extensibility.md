# Step 5: Operations, Deployment & Extensibility

This document provides a detailed technical breakdown of **Step 5** in the **Doc-QA Assistant** RAG pipeline. It covers operational workflows, running the system in production/development, configuring LLM providers, persistent storage maintenance, security checklists, and how to extend the pipeline with new document formats and embedding models.

---

## 1. Architectural Goal & Operational Flow

Step 5 defines how to manage, operate, monitor, and extend the complete Doc-QA Assistant system across both CLI and Web modes while maintaining security, data persistence, and architectural modularity.

```
[Doc-QA Assistant Core]
      ├── Operational Runners: Web Server (127.0.0.1:5000) & CLI (cli.py)
      ├── LLM Providers: Gemini, OpenRouter, OpenAI & Grounded Offline Mode
      ├── Storage Management: Persistent ChromaDB & Sandboxed Uploads
      └── Extensibility Hooks: Custom Parsers, Embedders & Vector Stores
```

---

## 2. Operations & Execution Guide

### A. Development & Production Run Targets ([`Makefile`](file:///home/remitpe/MAIN/rag-chat/Makefile))

The project includes standardized `make` targets for operational simplicity:

| Command | Action | Description |
| :--- | :--- | :--- |
| `make install` | `pip install -r requirements.txt` | Installs all Python 3.10 dependencies. |
| `make run` | `python -m app.main` | Starts the Flask Web Server on `http://127.0.0.1:5000`. |
| `make run-cli` | `python cli.py interactive` | Launches the interactive terminal Q&A shell. |
| `make eval` | `python cli.py evaluate` | Executes the automated benchmark evaluation suite. |
| `make test` | `pytest tests/ -v` | Runs the full 18-test unit and security suite. |

---

### B. Configuring LLM Providers & Environment ([`.env.example`](file:///home/remitpe/MAIN/rag-chat/.env.example))

The system dynamically adapts to whichever API keys are present in `.env`:

```bash
# Copy template to active environment
cp .env.example .env
```

```ini
# Google Gemini (Recommended for fast cloud generation)
GEMINI_API_KEY="AIza..."
LLM_MODEL="gemini/gemini-1.5-flash"

# OpenRouter (Access to Llama 3, Mistral, Claude, Gemini via single key)
# OPENROUTER_API_KEY="sk-or-v1-..."
# LLM_MODEL="openrouter/meta-llama/llama-3.1-8b-instruct"

# OpenAI
# OPENAI_API_KEY="sk-..."
# LLM_MODEL="gpt-4o-mini"

# Offline / Zero-Cost Mode (Default when no API keys are provided)
# The system runs a grounded factual extractor and executes guardrail refusals.
```

---

## 3. Persistent Storage Management

All vectors and metadata are stored on disk in `./data/chroma_db/`.

### Operational Maintenance Tasks:
1. **Inspecting Active Corpus**:
   ```bash
   python cli.py status
   ```
   *Displays total indexed chunks, collection name, document count, and persistence path.*
2. **Ingesting New Document Corpora**:
   ```bash
   python cli.py ingest /path/to/handbook.pdf --chunk-size 500 --overlap 50
   ```
3. **Resetting / Cleaning the Vector Store**:
   ```bash
   # Via CLI:
   python cli.py reset
   
   # Via REST API:
   curl -X POST http://127.0.0.1:5000/api/reset
   ```

---

## 4. Security & Hardening Checklist

When running Doc-QA Assistant, the following controls are enforced by default:

* **Localhost-Only Binding**: Web server strictly listens on `127.0.0.1:5000`. It explicitly rejects `0.0.0.0` bindings.
* **Secret Masking**: All logs passing through `SecretMaskingFormatter` automatically redact API keys matching `AIza...`, `sk-or-v1-...`, `sk-...`, or `Bearer ...`.
* **Zero XSS**: Frontend renders answers, citations, and metadata using native DOM properties (`textContent`, `document.createElement`, `replaceChildren`) rather than raw `innerHTML`.
* **Upload Sandboxing**: Uploaded files are checked for `%PDF-` and UTF-8 magic bytes, stripped of directory traversal tokens (`../`), limited to 10 MB, and stored in `./data/uploads/`.
* **CSP & Security Headers**: Native headers prevent clickjacking (`X-Frame-Options: DENY`) and MIME type sniffing (`X-Content-Type-Options: nosniff`).

---

## 5. Extensibility Guide: Adding New Capabilities

The modular architecture makes it straightforward to extend the pipeline:

### A. Adding a New Document Parser (e.g. Markdown or DOCX)
1. Open [`app/ingestion/parser.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/parser.py).
2. Create a new parsing function (e.g., `_parse_docx(file_path: Path) -> List[PageContent]`).
3. Register the extension in `DocumentParser.parse()`:
   ```python
   elif ext in {".docx"}:
       pages = self._parse_docx(path)
   ```
4. Add the extension to `ALLOWED_EXTENSIONS` in [`app/ingestion/validator.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/validator.py).

### B. Customizing Embedding Models
1. Open [`app/config.py`](file:///home/remitpe/MAIN/rag-chat/app/config.py) and [`app/embedding/embedder.py`](file:///home/remitpe/MAIN/rag-chat/app/embedding/embedder.py).
2. Change the default model name (e.g., to a multilingual or domain-specific sentence-transformer model).
3. The embedding dimensions and ChromaDB collection will update automatically on collection reset.

### C. Customizing Anti-Hallucination Guardrail Rules
1. Open [`app/augmentation/prompt_builder.py`](file:///home/remitpe/MAIN/rag-chat/app/augmentation/prompt_builder.py).
2. Edit `SYSTEM_INSTRUCTION_TEMPLATE` to tailor system rules, citation formats, or specific refusal phrases for your organization.

---

## 6. Summary of Step 5 Deliverables

| Deliverable | Description | Location |
| :--- | :--- | :--- |
| **Automation** | Standard `make` targets (`install`, `run`, `eval`, `test`) | [`Makefile`](file:///home/remitpe/MAIN/rag-chat/Makefile) |
| **Environment** | Configuration template for LLM providers & keys | [`.env.example`](file:///home/remitpe/MAIN/rag-chat/.env.example) |
| **CLI Operations** | Operational commands (`status`, `reset`, `ingest`) | [`cli.py`](file:///home/remitpe/MAIN/rag-chat/cli.py) |
| **Web Server** | Threaded Flask runtime bound to `127.0.0.1` | [`app/main.py`](file:///home/remitpe/MAIN/rag-chat/app/main.py) |
| **Security Layer** | CSP, secret masking, and upload validation | [`app/api/security.py`](file:///home/remitpe/MAIN/rag-chat/app/api/security.py) |
| **Documentation** | Architectural guides and roadmaps | [`docs/`](file:///home/remitpe/MAIN/rag-chat/docs/) |
