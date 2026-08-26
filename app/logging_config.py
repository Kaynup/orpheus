"""Structured logging configuration for Orpheus."""

from __future__ import annotations

import logging
import re
import sys
from typing import Optional

# Masking pattern for API keys or secrets
SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{35})"),           # Google/Gemini key pattern
    re.compile(r"(sk-or-v1-[0-9a-fA-F]{64})"),       # OpenRouter key pattern
    re.compile(r"(sk-[a-zA-Z0-9]{32,})"),            # OpenAI / generic key pattern
    re.compile(r"(Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*)"),
]


class SecretMaskingFormatter(logging.Formatter):
    """Custom log formatter that scrubs known API key patterns."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        masked = original
        for pattern in SECRET_PATTERNS:
            masked = pattern.sub("[REDACTED_SECRET]", masked)
        return masked


def setup_logger(
    name: str = "doc_qa",
    level: Optional[str] = None,
) -> logging.Logger:
    """Configure and return an application logger with secret masking."""
    logger = logging.getLogger(name)

    if level is None:
        level = "INFO"

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if already initialized
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        formatter = SecretMaskingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Ensure parent loggers don't duplicate
    logger.propagate = False
    return logger


logger = setup_logger()
