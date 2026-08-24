# Logging, Secret Masking, and Security in Doc-QA Assistant

This document explains the logging architecture of the **Doc-QA Assistant**, how secret masking works in [`app/logging_config.py`](file:///home/remitpe/MAIN/rag-chat/app/logging_config.py), why secrets must never leak into logs, and how log severity levels are structured.

---

## 1. Why Logging and Secret Protection Matter in GenAI Systems

In production GenAI and RAG applications, logs serve two critical purposes:
1. **Pipeline Observability & Debugging**: Allowing engineers to trace how documents are chunked, vectors are embedded, and queries are retrieved without needing interactive debuggers.
2. **Security & Compliance**: Ensuring that sensitive credentials (API keys, authorization headers, private user tokens) are never leaked to log files, cloud monitoring platforms (like Datadog/CloudWatch), or terminal outputs where unauthorized users could access them.

---

## 2. Deep Dive: What is in `logging_config.py`?

Let's examine each component of [`app/logging_config.py`](file:///home/remitpe/MAIN/rag-chat/app/logging_config.py):

### A. Secret Patterns Regex (`SECRET_PATTERNS`)

```python
SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{35})"),           # Google / Gemini API key pattern
    re.compile(r"(sk-or-v1-[0-9a-fA-F]{64})"),       # OpenRouter API key pattern
    re.compile(r"(sk-[a-zA-Z0-9]{32,})"),            # OpenAI / generic secret pattern
    re.compile(r"(Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*)"), # HTTP Authorization header tokens
]
```

#### What are these patterns?
* **Google / Gemini API Keys (`AIza...`)**: Google Cloud and Google AI Studio keys consistently start with `AIza` followed by 35 alphanumeric or hyphen/underscore characters.
* **OpenRouter Keys (`sk-or-v1-...`)**: OpenRouter API keys start with `sk-or-v1-` followed by a 64-character hexadecimal string.
* **OpenAI / General API Keys (`sk-...`)**: OpenAI secret keys start with `sk-` followed by 32+ alphanumeric characters.
* **Bearer Tokens (`Bearer ...`)**: Standard HTTP Authorization headers frequently carry sensitive OAuth or JWT session tokens.

---

### B. Custom Formatter with Secret Scrubbing (`SecretMaskingFormatter`)

```python
class SecretMaskingFormatter(logging.Formatter):
    """Custom log formatter that scrubs known API key patterns."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        masked = original
        for pattern in SECRET_PATTERNS:
            masked = pattern.sub("[REDACTED_SECRET]", masked)
        return masked
```

#### How does it work?
1. When any module logs a message (e.g. `logger.info(...)` or `logger.error(...)`), Python creates a `logging.LogRecord`.
2. Before the message is rendered to the console or log file, `SecretMaskingFormatter.format()` intercepts the formatted string.
3. It iterates over each compiled regular expression in `SECRET_PATTERNS`.
4. If a secret string matches (such as an API key passed in an error message or debugging dump), it is immediately replaced with `[REDACTED_SECRET]`.

#### Example in Action:
```text
# Raw text generated during an API failure:
"Failed to connect to Google API with key AIzaSyD3x918FkzLa9281Zlq019283748291823"

# What SecretMaskingFormatter actually outputs:
"2026-08-24 20:15:00 [ERROR] [doc_qa:42] Failed to connect to Google API with key [REDACTED_SECRET]"
```

---

### C. Structured Logger Setup (`setup_logger`)

```python
def setup_logger(
    name: str = "doc_qa",
    level: Optional[str] = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    ...
    handler = logging.StreamHandler(sys.stdout)
    formatter = SecretMaskingFormatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
```

#### Key Design Highlights:
* **Structured Timestamp & Source Line**: `%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s` clearly shows the date, exact time, log severity, file name, and line number where the log originated.
* **`propagate = False`**: Prevents log messages from bubbling up to root loggers, eliminating duplicate lines in the console.

---

## 3. Log Severity Levels Used in Doc-QA Assistant

The codebase strictly adheres to standard logging levels:

| Level | When to Use in Project | Example from Codebase |
| :--- | :--- | :--- |
| **`DEBUG`** | Fine-grained diagnostic information for developers during testing. | `logger.debug("Generating embedding for query: '%.60s...'")`<br>`logger.debug("Built augmented prompt for query '%s' with %d sources")` |
| **`INFO`** | Normal, meaningful pipeline lifecycle events. | `logger.info("Parsing document: %s (type: %s)")`<br>`logger.info("Created %d chunks for document '%s'")`<br>`logger.info("ChromaDB initialized. Current chunk count: %d")` |
| **`WARNING`** | Recoverable issues, low confidence, or fallback mode executions. | `logger.warning("Retrieval for query '%.50s' yielded no confident matches")`<br>`logger.warning("No active API keys found. Using offline generator.")` |
| **`ERROR`** | Failed operations, corrupt files, or unhandled exceptions. | `logger.error("Failed to parse PDF %s: %s")`<br>`logger.error("Vector search query failed: %s")`<br>`logger.error("LiteLLM generation failed for model '%s': %s")` |

---

## 4. Summary of Best Practices Enforced

1. **Never Hardcode Secrets**: Secrets are read exclusively from environment variables or `.env` and injected into the execution context.
2. **Scrub at the Logging Boundary**: Even if a third-party library (like LiteLLM or an HTTP client) prints a traceback with request headers, `SecretMaskingFormatter` strips the key before output.
3. **No Sensitive PII in Logs**: Document contents are truncated or previewed with length limits (`query[:40]`, `snippet[:80]`) rather than dumping megabytes of text into log streams.
