"""Unit tests for Flask API endpoints and security headers."""

import io
import pytest
from app.main import create_app


from app.api.security import save_uploaded_file, setup_cors
from app.config import config
from app.ingestion.validator import FileValidationError
from app.pipeline.rag_pipeline import RAGPipeline
from app.version import __version__
from werkzeug.datastructures import FileStorage


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_security_headers_present(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Content-Security-Policy" in res.headers
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_api_status_endpoint(client):
    """Verify status endpoint dynamically returns active version and collection configuration."""
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ready"
    assert data["version"] == __version__
    assert data["vector_store"]["collection_name"] == config.storage.collection_name
    assert data["config"]["default_model"] == config.llm.model
    assert data["config"]["default_top_k"] == config.retrieval.top_k


def test_api_query_empty(client):
    """Verify empty query string is rejected with explicit descriptive error message."""
    res = client.post("/api/query", json={"query": ""})
    assert res.status_code == 400
    assert "Query cannot be empty" in res.get_json()["error"]


def test_api_upload_invalid_type(client):
    data = {
        "file": (io.BytesIO(b"import os; os.system('ls')"), "malicious.py")
    }
    res = client.post("/api/ingest", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Unsupported file type" in res.get_json()["error"]


from app.api.security import CORS, save_uploaded_file, setup_cors


@pytest.mark.skipif(CORS is None, reason="flask-cors package is not installed in the environment")
def test_cors_preflight_whitelisted_origin(client):
    """Verify OPTIONS preflight request from a whitelisted origin receives CORS allow headers."""
    whitelisted_origin = config.server.cors_origins[0]
    headers = {
        "Origin": whitelisted_origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    }
    res = client.options("/api/query", headers=headers)
    assert res.headers.get("Access-Control-Allow-Origin") == whitelisted_origin
    assert res.headers.get("Access-Control-Allow-Credentials") == "true"


@pytest.mark.skipif(CORS is None, reason="flask-cors package is not installed in the environment")
def test_cors_preflight_forbidden_origin(client):
    """Verify OPTIONS preflight request from an untrusted origin is denied CORS headers."""
    untrusted_origin = "http://malicious-external-attacker.com"
    headers = {
        "Origin": untrusted_origin,
        "Access-Control-Request-Method": "POST",
    }
    res = client.options("/api/query", headers=headers)
    assert res.headers.get("Access-Control-Allow-Origin") != untrusted_origin


@pytest.mark.skipif(CORS is None, reason="flask-cors package is not installed in the environment")
def test_cors_non_api_route_not_exposed(client):
    """Verify non-API endpoints (e.g. index route) do not attach permissive CORS headers."""
    whitelisted_origin = config.server.cors_origins[0]
    res = client.get("/", headers={"Origin": whitelisted_origin})
    assert "Access-Control-Allow-Origin" not in res.headers


@pytest.mark.skipif(CORS is None, reason="flask-cors package is not installed in the environment")
def test_cors_custom_origins_configuration():
    """Verify setup_cors dynamically enforces custom allowed origins list."""
    custom_origin = "http://custom-frontend.internal:8080"
    app = create_app({"TESTING": True})
    setup_cors(app, allowed_origins=[custom_origin])

    with app.test_client() as custom_client:
        res = custom_client.options(
            "/api/status",
            headers={"Origin": custom_origin, "Access-Control-Request-Method": "GET"},
        )
        assert res.headers.get("Access-Control-Allow-Origin") == custom_origin


def test_create_app_with_custom_injected_pipeline():
    """Verify create_app correctly injects custom pipeline instance into app.extensions."""
    custom_pipeline = RAGPipeline()
    app = create_app(test_config={"TESTING": True}, pipeline=custom_pipeline)

    assert "rag_pipeline" in app.extensions
    assert app.extensions["rag_pipeline"] is custom_pipeline

    with app.test_client() as test_client:
        res = test_client.get("/api/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "ready"


def test_save_uploaded_file_path_traversal_sanitization(tmp_path):
    """Verify save_uploaded_file safely sanitizes path traversal attempts and stays within target directory."""
    raw_content = b"Sanitization content verification"
    file_storage = FileStorage(
        stream=io.BytesIO(raw_content),
        filename="../../../traversal_target.txt",
        content_type="text/plain",
    )

    saved_path, safe_name = save_uploaded_file(file_storage, target_dir=str(tmp_path))
    assert safe_name == "traversal_target.txt"
    assert saved_path.exists()
    assert saved_path.is_file()
    assert str(saved_path).startswith(str(tmp_path.resolve()))
    assert saved_path.read_bytes() == raw_content


def test_save_uploaded_file_empty_file_rejected(tmp_path):
    """Verify save_uploaded_file rejects empty 0-byte uploads and cleans up temporary file."""
    empty_storage = FileStorage(
        stream=io.BytesIO(b""),
        filename="empty_upload.txt",
        content_type="text/plain",
    )

    with pytest.raises(FileValidationError, match="File is empty"):
        save_uploaded_file(empty_storage, target_dir=str(tmp_path))

    # Assert no remnant file was left in the upload directory
    assert len(list(tmp_path.glob("*"))) == 0

