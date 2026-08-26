"""Security middleware and safe file management for Flask API."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from flask import Response
from werkzeug.datastructures import FileStorage

try:
    from flask_cors import CORS
except ImportError:
    CORS = None

from app.config import config
from app.ingestion.validator import (
    FileValidationError,
    sanitize_filename,
    validate_file,
)
from app.logging_config import logger


def setup_cors(app, allowed_origins: Optional[List[str]] = None) -> None:
    """Configure Flask-CORS with strict origin whitelisting on /api/* endpoints."""
    origins = allowed_origins or config.server.cors_origins
    if CORS is not None:
        CORS(
            app,
            resources={r"/api/*": {"origins": origins}},
            supports_credentials=True,
        )
        logger.info("Flask-CORS initialized for /api/* with allowed origins: %s", origins)
    else:
        logger.warning("flask_cors package not found; skipping automatic CORS attachment.")


def setup_security_headers(app):
    """Register response headers for strict Content Security Policy, nosniff, and anti-clickjacking."""

    @app.after_request
    def apply_security_headers(response: Response) -> Response:
        # Strict CSP policy allowing Google fonts and safe local scripts/styles
        csp_directives = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


def save_uploaded_file(file: FileStorage, target_dir: Optional[str] = None) -> Tuple[Path, str]:
    """
    Safely save an uploaded file with path traversal protection,
    unique identifier prefix, and size/format validation.
    """
    if not file or not file.filename:
        raise FileValidationError("No file selected for upload.")

    safe_name = sanitize_filename(file.filename)
    dest_dir = Path(target_dir or config.storage.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Prefix with short UUID to avoid collisions while keeping readable name
    unique_filename = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    final_path = dest_dir / unique_filename

    # Ensure path stays strictly inside upload directory (directory traversal safeguard)
    resolved_path = final_path.resolve()
    resolved_dest = dest_dir.resolve()
    if not str(resolved_path).startswith(str(resolved_dest) + os.path.sep):
        raise FileValidationError("Invalid upload destination path.")

    # Save to disk
    file.save(str(final_path))
    logger.info("Saved uploaded file to: %s", final_path)

    # Validate uploaded file
    try:
        validate_file(final_path)
    except Exception as err:
        # Delete invalid file immediately
        if final_path.exists():
            final_path.unlink()
        raise err

    return final_path, safe_name
