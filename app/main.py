"""Flask Application entry point for Orpheus."""

from __future__ import annotations

from pathlib import Path

from flask import Flask

# Compatibility shims for Python 3.10 and older Linux sqlite3
try:
    __import__("pysqlite3")
    import sys

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import typing

try:
    import typing_extensions

    if not hasattr(typing, "NotRequired"):
        typing.NotRequired = getattr(typing_extensions, "NotRequired", None)
    if not hasattr(typing, "Required"):
        typing.Required = getattr(typing_extensions, "Required", None)
except ImportError:
    pass

from app.api.routes import api_bp
from app.api.security import setup_cors, setup_security_headers
from app.config import config
from app.logging_config import logger
from app.pipeline.rag_pipeline import RAGPipeline

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(test_config: dict = None, pipeline: RAGPipeline | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "app" / "static"),
    )

    # Configuration defaults from AppConfig
    app.config.update(
        MAX_CONTENT_LENGTH=config.server.max_content_length,
        SECRET_KEY=config.server.secret_key,
    )

    if test_config:
        app.config.update(test_config)

    # Attach RAG Pipeline instance
    if pipeline is None:
        pipeline = RAGPipeline()
    app.extensions["rag_pipeline"] = pipeline

    # Attach security middleware & CORS
    setup_security_headers(app)
    setup_cors(app)

    # Register API blueprint
    app.register_blueprint(api_bp)

    logger.info("Flask application initialized.")
    return app


def main():
    """Run the Flask development server on localhost."""
    app = create_app()
    host = config.server.host
    # Strictly enforce 127.0.0.1
    if host == "0.0.0.0":
        host = "127.0.0.1"

    port = config.server.port
    logger.info("Starting Orpheus Server on http://%s:%d", host, port)
    app.run(host=host, port=port, debug=config.server.debug, threaded=True)


if __name__ == "__main__":
    main()
