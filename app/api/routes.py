"""Flask API routes for Orpheus with real-time SSE stream synchronization."""

from __future__ import annotations

import json
import os
import queue
import threading
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from flask import Blueprint, Response, jsonify, render_template, request, send_file

from app.api.security import save_uploaded_file
from app.config import config
from app.evaluation.evaluator import RAGEvaluator
from app.logging_config import logger
from app.pipeline.base import BaseRAGPipeline
from app.pipeline.events import PipelineEvent
from app.pipeline.factory import create_rag_pipeline
from app.pipeline.rag_pipeline import IngestionResult, QueryResult

api_bp = Blueprint("api", __name__)

_default_pipeline: BaseRAGPipeline | None = None


def resolve_model_item(model_str: str, source_badge: str = "Configured") -> dict[str, str]:
    """Parse any model identifier string into a standardized model object with clean metadata."""
    model_str = model_str.strip()
    if "/" in model_str:
        provider_key, raw_name = model_str.split("/", 1)
    else:
        provider_key, raw_name = "custom", model_str

    pk = provider_key.lower()
    if pk in ("gemini", "google"):
        provider = "Google Cloud"
        name = f"Google Gemini ({raw_name})"
    elif pk == "openrouter":
        provider = "OpenRouter"
        name = f"OpenRouter / {raw_name}"
    elif pk in ("openai", "gpt"):
        provider = "OpenAI"
        name = f"OpenAI / {raw_name}"
    elif pk == "ollama":
        provider = "Ollama Local"
        name = f"Ollama / {raw_name}"
    elif pk == "offline":
        provider = "Local Extractor"
        name = "Offline Grounded Extractor"
        source_badge = "No Key Required"
    else:
        provider = provider_key.capitalize()
        name = f"{provider} / {raw_name}"

    return {
        "id": model_str,
        "name": name,
        "provider": provider,
        "badge": source_badge,
    }


def get_available_models() -> list[dict[str, str]]:
    """
    Discover available LLM models dynamically:
    1. Reads live .env variables ending with '_MODEL' or containing '_MODEL'.
    2. Probes local Ollama instance for pulled models.
    3. Guarantees Offline Grounded Extractor fallback.
    """
    dotenv_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=True)

    models: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    def add_model(model_dict: dict[str, str]):
        m_id = model_dict["id"]
        if m_id not in seen_ids:
            seen_ids.add(m_id)
            models.append(model_dict)

    # 1. Extract all environment variables containing '_MODEL' (e.g. LLM_MODEL, GEMINI_MODEL, OLLAMA_MODEL, etc.)
    for key, val in os.environ.items():
        if "_MODEL" in key and val and val.strip():
            val = val.strip()
            for single_model in val.split(","):
                single_model = single_model.strip()
                if single_model:
                    badge = "Default" if key == "LLM_MODEL" else "Configured"
                    add_model(resolve_model_item(single_model, source_badge=badge))

    # 2. Probe Ollama daemon if running for pulled models
    ollama_urls = []
    if config.llm.ollama_api_base:
        ollama_urls.append(config.llm.ollama_api_base.rstrip("/"))
    if os.getenv("OLLAMA_API_BASE"):
        ollama_urls.append(os.getenv("OLLAMA_API_BASE").rstrip("/"))
    ollama_urls.extend(["http://127.0.0.1:11434", "http://localhost:11434"])

    for base_url in dict.fromkeys(ollama_urls):
        try:
            req = urllib.request.Request(
                f"{base_url}/api/tags",
                headers={"User-Agent": "Orpheus/0.2.0"},
            )
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status == 200:
                    raw_data = response.read().decode("utf-8")
                    payload = json.loads(raw_data)
                    installed_models = payload.get("models", [])
                    for item in installed_models:
                        raw_name = item.get("name") or item.get("model")
                        if not raw_name:
                            continue
                        clean_tag = raw_name.replace("ollama/", "")
                        model_id = f"ollama/{clean_tag}"
                        details = item.get("details") or {}
                        param_size = details.get("parameter_size")
                        badge_text = f"Local ({param_size})" if param_size else "Local Service"
                        add_model(
                            {
                                "id": model_id,
                                "name": f"Ollama / {clean_tag}",
                                "provider": "Ollama Local",
                                "badge": badge_text,
                            }
                        )
                    break
        except Exception:
            continue

    # 3. Always include Offline Grounded Extractor
    add_model(
        {
            "id": "offline",
            "name": "Offline Grounded Extractor",
            "provider": "Local Extractor",
            "badge": "No Key Required",
        }
    )

    return models


def get_pipeline() -> BaseRAGPipeline:
    """Retrieve the RAGPipeline instance from current Flask application context or fallback."""
    from flask import current_app

    try:
        if current_app:
            pipeline = current_app.extensions.get("rag_pipeline")
            if pipeline is not None:
                return pipeline
    except RuntimeError:
        pass

    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = create_rag_pipeline()
    return _default_pipeline


@api_bp.route("/favicon.ico")
@api_bp.route("/favicon.png")
@api_bp.route("/assets/favicon.png")
@api_bp.route("/static/favicon.png")
def favicon():
    """Serve application favicon from assets directory."""
    root_dir = Path(__file__).resolve().parent.parent.parent
    assets_dir = root_dir / "assets"
    favicon_path = assets_dir / "favicon.png"

    if not favicon_path.exists():
        root_favicon = root_dir / "favicon.png"
        if root_favicon.exists():
            try:
                import shutil

                assets_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root_favicon, favicon_path)
            except Exception:
                favicon_path = root_favicon

    if favicon_path.exists():
        return send_file(favicon_path, mimetype="image/png")
    return Response(status=404)


@api_bp.route("/", methods=["GET"])
def index():
    """Render the single-page Orpheus web application."""
    return render_template("index.html", version=config.version)


@api_bp.route("/api/status", methods=["GET"])
def get_status():
    """Return persistent vector database status and configuration."""
    dotenv_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=True)

    pipeline = get_pipeline()
    stats = pipeline.vector_store.get_collection_stats()
    samples_dir = Path(config.storage.samples_dir)
    sample_files = [f.name for f in samples_dir.glob("*.*")] if samples_dir.exists() else []

    current_default_model = os.getenv("LLM_MODEL") or config.llm.model

    return jsonify(
        {
            "status": "ready",
            "version": config.version,
            "vector_store": stats,
            "sample_files": sample_files,
            "available_models": get_available_models(),
            "config": {
                "default_model": current_default_model,
                "default_top_k": config.retrieval.top_k,
                "default_chunk_size": config.chunk.chunk_size,
                "default_chunk_overlap": config.chunk.chunk_overlap,
                "has_gemini_key": bool(
                    os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or config.llm.gemini_api_key
                ),
                "has_openrouter_key": bool(os.getenv("OPENROUTER_API_KEY") or config.llm.openrouter_api_key),
                "has_openai_key": bool(os.getenv("OPENAI_API_KEY") or config.llm.openai_api_key),
            },
        }
    )


@api_bp.route("/api/documents", methods=["GET"])
def list_documents():
    """List all indexed documents with metadata summary."""
    pipeline = get_pipeline()
    docs = pipeline.vector_store.list_documents()
    return jsonify({"documents": docs, "total": len(docs)})


@api_bp.route("/api/documents/<doc_id>", methods=["DELETE"])
def delete_document(doc_id: str):
    """Delete a document by ID."""
    pipeline = get_pipeline()
    deleted = pipeline.vector_store.delete_document(doc_id)
    return jsonify({"success": True, "deleted_chunks": deleted})


@api_bp.route("/api/ingest", methods=["POST"])
def ingest_file():
    """Upload and ingest a document file (.txt or .pdf)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    chunk_size = request.form.get("chunk_size", type=int)
    chunk_overlap = request.form.get("chunk_overlap", type=int)

    try:
        saved_path, safe_name = save_uploaded_file(file)
        pipeline = get_pipeline()
        result: IngestionResult = pipeline.ingest_document(
            file_path=saved_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return jsonify({"success": True, "result": result.to_dict()})
    except Exception as err:
        logger.error("Ingestion endpoint failed: %s", err)
        return jsonify({"error": str(err)}), 400


@api_bp.route("/api/ingest/stream", methods=["POST"])
def ingest_file_stream():
    """
    Upload and ingest a document with Server-Sent Events (SSE) streaming real backend events.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    chunk_size = request.form.get("chunk_size", type=int)
    chunk_overlap = request.form.get("chunk_overlap", type=int)

    try:
        saved_path, safe_name = save_uploaded_file(file)
    except Exception as err:
        return jsonify({"error": str(err)}), 400

    pipeline = get_pipeline()
    event_queue: queue.Queue = queue.Queue()

    def sse_event_callback(event: PipelineEvent):
        event_queue.put(event)

    def run_ingestion():
        try:
            res = pipeline.ingest_document(
                file_path=saved_path,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                event_callback=sse_event_callback,
            )
            event_queue.put({"__FINAL_RESULT__": res.to_dict()})
        except Exception as err:
            event_queue.put({"__ERROR__": str(err)})
        finally:
            event_queue.put(None)  # Sentinel to end stream

    threading.Thread(target=run_ingestion, daemon=True).start()

    def generate_sse():
        while True:
            item = event_queue.get()
            if item is None:
                break
            if isinstance(item, dict):
                yield f"data: {json.dumps(item)}\n\n"
            elif isinstance(item, PipelineEvent):
                yield f"data: {json.dumps({'event': item.to_dict()})}\n\n"

    return Response(generate_sse(), mimetype="text/event-stream")


@api_bp.route("/api/query", methods=["POST"])
def query():
    """Submit question and receive grounded answer with inspectable context and citations."""
    data = request.get_json() or {}
    question = data.get("query", "").strip()
    if not question:
        return jsonify({"error": "Query cannot be empty"}), 400

    top_k = data.get("top_k", config.retrieval.top_k)
    score_threshold = data.get("score_threshold", config.retrieval.score_threshold)
    model = data.get("model")
    temperature = data.get("temperature")

    try:
        pipeline = get_pipeline()
        result: QueryResult = pipeline.answer_query(
            query=question,
            top_k=top_k,
            score_threshold=score_threshold,
            model=model,
            temperature=temperature,
        )
        return jsonify({"success": True, "result": result.to_dict()})
    except Exception as err:
        logger.error("Query endpoint failed: %s", err)
        return jsonify({"error": str(err)}), 500


@api_bp.route("/api/query/stream", methods=["POST"])
def query_stream():
    """
    Stream real QA pipeline stage transitions and final answer via Server-Sent Events (SSE).
    """
    data = request.get_json() or {}
    question = data.get("query", "").strip()
    if not question:
        return jsonify({"error": "Query cannot be empty"}), 400

    top_k = data.get("top_k", config.retrieval.top_k)
    score_threshold = data.get("score_threshold", config.retrieval.score_threshold)
    model = data.get("model")
    temperature = data.get("temperature")

    pipeline = get_pipeline()
    event_queue: queue.Queue = queue.Queue()

    def sse_event_callback(event: PipelineEvent):
        event_queue.put(event)

    def run_query():
        try:
            res = pipeline.answer_query(
                query=question,
                top_k=top_k,
                score_threshold=score_threshold,
                model=model,
                temperature=temperature,
                event_callback=sse_event_callback,
            )
            event_queue.put({"__FINAL_RESULT__": res.to_dict()})
        except Exception as err:
            event_queue.put({"__ERROR__": str(err)})
        finally:
            event_queue.put(None)

    threading.Thread(target=run_query, daemon=True).start()

    def generate_sse():
        while True:
            item = event_queue.get()
            if item is None:
                break
            if isinstance(item, dict):
                yield f"data: {json.dumps(item)}\n\n"
            elif isinstance(item, PipelineEvent):
                yield f"data: {json.dumps({'event': item.to_dict()})}\n\n"

    return Response(generate_sse(), mimetype="text/event-stream")


@api_bp.route("/api/samples", methods=["POST"])
def ingest_samples():
    """Ingest all sample documents in data/sample_documents/."""
    samples_dir = Path(config.storage.samples_dir)
    if not samples_dir.exists():
        return jsonify({"error": "Sample documents folder not found"}), 404

    files = sorted(list(samples_dir.glob("*.txt")) + list(samples_dir.glob("*.pdf")))
    results = []
    pipeline = get_pipeline()
    for f in files:
        try:
            res = pipeline.ingest_document(f)
            results.append({"filename": f.name, "chunks": res.chunk_count, "status": "success"})
        except Exception as err:
            results.append({"filename": f.name, "error": str(err), "status": "failed"})

    return jsonify({"success": True, "ingested": results})


@api_bp.route("/api/evaluate", methods=["POST"])
def evaluate_benchmark():
    """Run the 10 benchmark test cases and return the full evaluation report."""
    try:
        pipeline = get_pipeline()
        evaluator = RAGEvaluator(pipeline)
        report = evaluator.run_benchmark()
        return jsonify({"success": True, "report": report.to_dict()})
    except Exception as err:
        logger.error("Evaluation endpoint failed: %s", err)
        return jsonify({"error": str(err)}), 500


@api_bp.route("/api/reset", methods=["POST"])
def reset_vector_store():
    """Reset and clear all vectors in the collection."""
    try:
        pipeline = get_pipeline()
        pipeline.vector_store.reset_collection()
        return jsonify({"success": True, "message": "Vector store reset successfully."})
    except Exception as err:
        return jsonify({"error": str(err)}), 500
