"""Configuration management for Doc-QA Assistant."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class ChunkConfig:
    """Settings for text chunking."""
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: List[str] = field(default_factory=lambda: ["\n\n", "\n", ". ", "? ", "! ", " ", ""])

    def __post_init__(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")


@dataclass
class RetrievalConfig:
    """Settings for semantic retrieval."""
    top_k: int = 3
    # Distance threshold (lower distance means higher semantic similarity)
    # Documents with distance > score_threshold are considered low confidence
    score_threshold: float = 0.90


@dataclass
class LLMConfig:
    """Settings for LLM generation via LiteLLM."""
    model: str = "gemini/gemini-1.5-flash"
    temperature: float = 0.2
    max_tokens: int = 1024
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ollama_api_base: Optional[str] = "http://localhost:11434"


@dataclass
class StorageConfig:
    """Settings for persistent ChromaDB and uploads."""
    persist_dir: str = str(BASE_DIR / "data" / "chroma_db")
    collection_name: str = "doc_qa_collection"
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    samples_dir: str = str(BASE_DIR / "data" / "sample_documents")
    # Ingestion limits
    allowed_extensions: List[str] = field(default_factory=lambda: [".txt", ".pdf"])
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    hash_buffer_size: int = 65536  # 64 KB read chunks for SHA-256


@dataclass
class ServerConfig:
    """Settings for Flask web server."""
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    log_level: str = "INFO"
    max_content_length: int = 16 * 1024 * 1024  # 16 MB max payload
    secret_key: Optional[str] = None


from app.version import __version__


@dataclass
class AppConfig:
    """Master application configuration."""
    version: str = __version__
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    @classmethod
    def from_env(cls) -> AppConfig:
        """Construct configuration by reading environment variables with robust defaults."""
        chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "500"))
        chunk_overlap = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
        separators_env = os.getenv("RAG_CHUNK_SEPARATORS")
        if separators_env:
            try:
                chunk_separators = json.loads(separators_env)
                if not isinstance(chunk_separators, list):
                    raise ValueError
            except Exception:
                chunk_separators = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]
        else:
            chunk_separators = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

        top_k = int(os.getenv("RAG_TOP_K", "3"))
        score_threshold = float(os.getenv("RAG_SCORE_THRESHOLD", "0.90"))

        llm_model = os.getenv("LLM_MODEL", "gemini/gemini-1.5-flash")
        llm_temp = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))

        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        ollama_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

        persist_dir = os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "data" / "chroma_db"))
        collection_name = os.getenv("CHROMA_COLLECTION_NAME", "doc_qa_collection")
        upload_dir = os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))

        # Ingestion limits
        raw_extensions = os.getenv("RAG_ALLOWED_EXTENSIONS", ".txt,.pdf")
        allowed_extensions = [
            ext.strip() if ext.strip().startswith(".") else f".{ext.strip()}"
            for ext in raw_extensions.split(",")
            if ext.strip()
        ]
        max_file_size_mb = int(os.getenv("RAG_MAX_FILE_SIZE_MB", "10"))
        max_file_size_bytes = max_file_size_mb * 1024 * 1024
        hash_buffer_size = int(os.getenv("RAG_HASH_BUFFER_SIZE", "65536"))

        server_host = os.getenv("SERVER_HOST", "127.0.0.1")
        # Enforce localhost/127.0.0.1 for security compliance
        if server_host == "0.0.0.0":
            server_host = "127.0.0.1"
        server_port = int(os.getenv("SERVER_PORT", "5000"))
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
        secret_key = os.getenv("SECRET_KEY") or os.urandom(32).hex()

        return cls(
            version=__version__,
            chunk=ChunkConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=chunk_separators),
            retrieval=RetrievalConfig(top_k=top_k, score_threshold=score_threshold),
            llm=LLMConfig(
                model=llm_model,
                temperature=llm_temp,
                max_tokens=llm_max_tokens,
                gemini_api_key=gemini_key,
                openrouter_api_key=openrouter_key,
                openai_api_key=openai_key,
                ollama_api_base=ollama_base,
            ),
            storage=StorageConfig(
                persist_dir=persist_dir,
                collection_name=collection_name,
                upload_dir=upload_dir,
                allowed_extensions=allowed_extensions,
                max_file_size_bytes=max_file_size_bytes,
                hash_buffer_size=hash_buffer_size,
            ),
            server=ServerConfig(
                host=server_host,
                port=server_port,
                log_level=log_level,
                max_content_length=max_content_length,
                secret_key=secret_key,
            ),
        )


# Global default configuration instance
config = AppConfig.from_env()
