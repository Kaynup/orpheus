"""Unit tests for Flask API endpoints and security headers."""

import io
import pytest
from app.main import create_app


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


def test_api_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ready"
    assert "vector_store" in data
    assert "config" in data


def test_api_query_empty(client):
    res = client.post("/api/query", json={"query": ""})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_api_upload_invalid_type(client):
    data = {
        "file": (io.BytesIO(b"import os; os.system('ls')"), "malicious.py")
    }
    res = client.post("/api/ingest", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert "Unsupported file type" in res.get_json()["error"]
