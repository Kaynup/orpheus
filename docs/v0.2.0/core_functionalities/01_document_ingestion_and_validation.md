# Document Ingestion & Validation Subsystem

**BRD Requirements Addressed**:
* **FR1**: System shall accept multiple document uploads (`.txt`, `.pdf`).
* **NFR1**: Codebase should be modular (separate ingestion, retrieval, generation components).
* **NFR5**: API keys and inputs must be handled securely (path traversal prevention, sanitization, input validation).

---

## 1. Overview & Architectural Role

The **Document Ingestion & Validation Subsystem** is the entry gate for all knowledge entering the Orpheus RAG system. It is responsible for accepting raw document files from the Flask REST/SSE API, web UI dropzone, or CLI, performing defensive security and validation checks, extracting clean text with structural page-level metadata, computing deduplication checksums, and generating a standardized `ParsedDocument` representation.

In v0.2.0, this subsystem was completely refactored from a monolithic branching script into an **Open-Closed Principle (OCP) compliant Strategy Pattern** centered around `BaseDocumentParser` and a dynamic `PARSER_REGISTRY`.

```mermaid
graph TD
    subgraph ClientLayer ["Client & Upload Layer"]
        CLI["CLI Tool (cli.py)"]
        WebUI["Web Dropzone (ingestion.js)"]
        REST["REST API POST /api/ingest"]
    end

    subgraph SecurityLayer ["Security & Validation Layer (validator.py)"]
        Sanitize["sanitize_filename()"]
        CheckPath["Path Traversal Defense"]
        SizeCheck["Dynamic Size Limit (RAG_MAX_FILE_SIZE_MB)"]
        ExtCheck["Allowed Extension Filter (RAG_ALLOWED_EXTENSIONS)"]
    end

    subgraph IngestionCore ["Ingestion & Parsing Core (parser.py)"]
        HashEngine["Streaming SHA-256 Checksum (compute_sha256)"]
        UUIDGen["Deterministic UUID5 doc_id Generation"]
        Registry{"PARSER_REGISTRY Dispatch"}
        TXTParser["TXTDocumentParser (UTF-8 / Fallback)"]
        PDFParser["PDFDocumentParser (pypdf Engine)"]
    end

    subgraph OutputModel ["Structured Data Model"]
        ParsedDoc["ParsedDocument Dataclass"]
        PagesList["List[PageContent]"]
    end

    CLI --> Sanitize
    WebUI --> Sanitize
    REST --> Sanitize

    Sanitize --> CheckPath
    CheckPath --> SizeCheck
    SizeCheck --> ExtCheck

    ExtCheck --> HashEngine
    HashEngine --> UUIDGen
    UUIDGen --> Registry

    Registry -- ".txt" --> TXTParser
    Registry -- ".pdf" --> PDFParser

    TXTParser --> ParsedDoc
    PDFParser --> ParsedDoc
    ParsedDoc --> PagesList
```

---

## 2. Ingestion Lifecycle & Step-by-Step Flow

### 2.1 Forward Execution Flow
When a document is ingested, the system executes the following linear stages:

1. **Filename Sanitization (`sanitize_filename`)**:
   - Strips directory traversal sequences (`../`, `..\`), special characters, and path separators.
   - Preserves alphanumeric characters, dashes, underscores, and dots.
   - Falls back to `unnamed_.txt` if sanitization results in an empty string.
2. **File Validation (`validate_file`)**:
   - Asserts file existence and confirms the path is a regular file.
   - Checks file size against dynamic `config.storage.max_file_size_bytes` (default 10 MB, configurable via `RAG_MAX_FILE_SIZE_MB`). Rejects 0-byte empty files.
   - Validates file extension against `config.storage.allowed_extensions` (default `[".txt", ".pdf"]`, configurable via `RAG_ALLOWED_EXTENSIONS`).
3. **Streaming SHA-256 Checksum Calculation (`compute_sha256`)**:
   - Reads the file in chunks of `config.storage.hash_buffer_size` (default 64 KB = 65,536 bytes, configurable via `RAG_HASH_BUFFER_SIZE`).
   - Ensures constant memory overhead even for large multi-megabyte PDF manuals.
4. **Deterministic Document ID Generation**:
   - Generates a `UUID5` using the standard URL namespace and the SHA-256 checksum:
     $$\text{doc\_id} = \text{UUID5}(\text{NAMESPACE\_URL}, \text{"file://" + checksum})$$
   - Guaranteed deduplication: uploading the identical file under a different name produces the exact same `doc_id`.
5. **Strategy Resolution & Parsing**:
   - Extracts `file_path.suffix.lower()`.
   - Looks up parser in `PARSER_REGISTRY[ext]`.
   - Executes strategy `parse(file_path)` to extract raw text, page boundaries, character counts, and metadata.
6. **`ParsedDocument` Assembly**:
   - Populates and returns `ParsedDocument` containing `doc_id`, `filename`, `file_type`, `file_path`, `total_chars`, `checksum`, `pages: List[PageContent]`, and format-specific `metadata`.

```mermaid
sequenceDiagram
    autonumber
    actor User as Client / User
    participant Route as Flask Route / Pipeline
    participant Validator as Ingestion Validator
    participant HashSys as SHA-256 Checksum
    participant Registry as PARSER_REGISTRY
    participant Strategy as Document Parser Strategy
    participant Store as Downstream Chunker

    User->>Route: Upload File (e.g. handbook.pdf)
    Route->>Validator: sanitize_filename("handbook.pdf")
    Validator-->>Route: Clean filename "handbook.pdf"
    
    Route->>Validator: validate_file(path, max_bytes, allowed_extensions)
    alt File missing / empty / too large / invalid ext
        Validator-->>Route: Raise FileValidationError
        Route-->>User: 400 Bad Request (JSON error)
    else File Valid
        Validator-->>Route: Validation Passed
    end

    Route->>HashSys: compute_sha256(path, buffer_size=65536)
    HashSys-->>Route: SHA-256 Digest (64-char hex)
    
    Route->>Registry: Lookup parser for extension ".pdf"
    alt Extension not in PARSER_REGISTRY
        Registry-->>Route: Raise DocumentParsingError
        Route-->>User: 400 Unsupported Format
    else Strategy Found
        Registry->>Strategy: PDFDocumentParser.parse(path)
        Strategy->>Strategy: Read pages via pypdf
        Strategy->>Strategy: Build List[PageContent]
        Strategy-->>Route: Return ParsedDocument
    end

    Route->>Store: Handover ParsedDocument to RecursiveTextSplitter
```

---

## 3. Parser Strategy Pattern & Extensible Registry (OCP)

### 3.1 Class Architecture
The parser hierarchy decouples document reading from format dispatching. Adding support for a new format (such as Markdown `.md` or Word `.docx`) requires **zero modifications** to `parse_document()` or existing parsers.

```mermaid
classDiagram
    class BaseDocumentParser {
        <<abstract>>
        +parse(file_path: Path) ParsedDocument*
    }

    class TXTDocumentParser {
        +parse(file_path: Path) ParsedDocument
    }

    class PDFDocumentParser {
        +parse(file_path: Path) ParsedDocument
    }

    class CustomMarkdownParser {
        +parse(file_path: Path) ParsedDocument
    }

    class PARSER_REGISTRY {
        <<dictionary>>
        +".txt": TXTDocumentParser
        +".pdf": PDFDocumentParser
        +".md": CustomMarkdownParser
    }

    class ParsedDocument {
        +str doc_id
        +str filename
        +str file_type
        +str file_path
        +int total_chars
        +str checksum
        +List~PageContent~ pages
        +Dict metadata
        +full_text: str
    }

    class PageContent {
        +int page_number
        +str text
        +int char_count
    }

    BaseDocumentParser <|-- TXTDocumentParser
    BaseDocumentParser <|-- PDFDocumentParser
    BaseDocumentParser <|-- CustomMarkdownParser
    PARSER_REGISTRY o-- BaseDocumentParser : contains
    TXTDocumentParser ..> ParsedDocument : creates
    PDFDocumentParser ..> ParsedDocument : creates
    ParsedDocument *-- PageContent : aggregates
```

### 3.2 Strategy Implementation Details

#### `TXTDocumentParser`
- Reads plain text files using `utf-8` encoding with `errors="replace"` fallback to prevent crashes on non-standard encoding bytes.
- Wraps entire content as page 1 (`PageContent(page_number=1, text=clean_text, char_count=len(clean_text))`).
- Populates metadata with `line_count` and `encoding`.

#### `PDFDocumentParser`
- Uses `pypdf.PdfReader` to extract text page-by-page.
- Tracks `page_number` (1-indexed) per page.
- Rejects corrupt or 0-page PDFs with `DocumentParsingError`.
- Records total character count and `page_count` in metadata.

#### Dynamic Extension Registration
```python
# Extending to support Markdown (.md) without modifying core code:
class MarkdownDocumentParser(BaseDocumentParser):
    def parse(self, file_path: Path) -> ParsedDocument:
        # custom parsing logic...
        ...

# One-line registration:
PARSER_REGISTRY[".md"] = MarkdownDocumentParser()
```

---

## 4. Error Handling & Backward Recovery Flow

The ingestion pipeline incorporates fail-fast, defensive error handling to prevent corrupt data from reaching the vector store:

```mermaid
graph TD
    StartIngest["Start Ingest Request"] --> ValidateFile{"validate_file()"}
    
    ValidateFile -- "Nonexistent / Dir" --> ErrNotFound["Raise FileValidationError<br>(File not found)"]
    ValidateFile -- "Size == 0 bytes" --> ErrEmpty["Raise FileValidationError<br>(File is empty)"]
    ValidateFile -- "Size > Max Size" --> ErrSize["Raise FileValidationError<br>(File exceeds limit)"]
    ValidateFile -- "Ext not whitelisted" --> ErrExt["Raise FileValidationError<br>(Unsupported extension)"]
    
    ValidateFile -- "Passed" --> DispatchStrategy{"PARSER_REGISTRY.get(ext)"}
    
    DispatchStrategy -- "None" --> ErrUnregistered["Raise DocumentParsingError<br>(No registered parser)"]
    DispatchStrategy -- "Strategy Found" --> ParseExec{"Parser.parse()"}
    
    ParseExec -- "Corrupt File / pypdf error" --> ErrCorrupt["Raise DocumentParsingError<br>(Failed to parse doc)"]
    ParseExec -- "Success" --> Complete["Return ParsedDocument"]

    subgraph ErrorHandling ["Rollback & Client Notification"]
        ErrNotFound --> CleanTmp["Clean temporary upload files"]
        ErrEmpty --> CleanTmp
        ErrSize --> CleanTmp
        ErrExt --> CleanTmp
        ErrUnregistered --> CleanTmp
        ErrCorrupt --> CleanTmp
        CleanTmp --> EmitEvent["Emit EventStage.PIPELINE_FAILED"]
        EmitEvent --> HttpErr["Return HTTP 400 / CLI Error Message"]
    end
```

---

## 5. Configuration Reference

| Environment Variable | Config Property | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `RAG_ALLOWED_EXTENSIONS` | `config.storage.allowed_extensions` | `List[str]` | `[".txt", ".pdf"]` | Comma-separated list of permitted document extensions. |
| `RAG_MAX_FILE_SIZE_MB` | `config.storage.max_file_size_bytes` | `int` | `10485760` (10 MB) | Maximum upload file size in megabytes, stored as bytes. |
| `RAG_HASH_BUFFER_SIZE` | `config.storage.hash_buffer_size` | `int` | `65536` (64 KB) | Buffer chunk size for streaming SHA-256 calculation. |
| `UPLOAD_DIR` | `config.storage.upload_dir` | `str` | `data/uploads` | Designated filesystem destination for uploaded documents. |

---

## 6. Verification & Automated Tests

The ingestion and validation subsystem is verified by 9 collocated unit tests in [`app/ingestion/tests/test_ingestion.py`](file:///home/remitpe/MAIN/rag-chat/app/ingestion/tests/test_ingestion.py):
* `test_sanitize_filename`: Path traversal strings (`../../../etc/passwd`) and Windows separators are stripped to a safe basename.
* `test_validate_nonexistent_file`: Nonexistent file paths raise `FileValidationError`.
* `test_validate_empty_file`: 0-byte files raise `FileValidationError`.
* `test_validate_invalid_extension`: Unpermitted file extensions raise `FileValidationError`.
* `test_validate_dynamic_size_limit`: Dynamically checks rejection when file exceeds `max_bytes` and acceptance when within limit.
* `test_validate_dynamic_allowed_extensions`: Custom allowed extension overrides dynamically validated.
* `test_compute_sha256_buffer_invariance`: Asserts identical 64-character hex digests across varying buffer sizes (64B, default, 2x).
* `test_parse_valid_txt`: Verifies full `ParsedDocument` round-trip for text files.
* `test_parser_registry_dynamic_extensibility`: Registers a custom parser, verifies parsing, and cleanly removes it in a `finally` block (OCP contract test).
