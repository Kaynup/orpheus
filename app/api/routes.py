"""Flask API routes for Doc-QA Assistant with real-time SSE stream synchronization."""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Generator
from flask import Blueprint, Response, jsonify, render_template, request

from app.api.security import save_uploaded_file
from app.config import config
from app.evaluation.evaluator import RAGEvaluator
from app.logging_config import logger
from app.pipeline.events import EventStage, EventStatus, PipelineEvent
from app.pipeline.rag_pipeline import IngestionResult, QueryResult, RAGPipeline

api_bp = Blueprint("api", __name__)

_default_pipeline: RAGPipeline | None = None


def get_pipeline() -> RAGPipeline:
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
        _default_pipeline = RAGPipeline()
    return _default_pipeline


@api_bp.route("/")
def index():
    """Render the single-page Doc-QA web application."""
    return render_template("index.html", version=config.version)


@api_bp.route("/api/status", methods=["GET"])
def get_status():
    """Return persistent vector database status and configuration."""
    pipeline = get_pipeline()
    stats = pipeline.vector_store.get_collection_stats()
    samples_dir = Path(config.storage.samples_dir)
    sample_files = [f.name for f in samples_dir.glob("*.*")] if samples_dir.exists() else []

    return jsonify({
        "status": "ready",
        "version": config.version,
        "vector_store": stats,
        "sample_files": sample_files,
        "config": {
            "default_model": config.llm.model,
            "default_top_k": config.retrieval.top_k,
            "default_chunk_size": config.chunk.chunk_size,
            "default_chunk_overlap": config.chunk.chunk_overlap,
            "has_gemini_key": bool(config.llm.gemini_api_key),
            "has_openrouter_key": bool(config.llm.openrouter_api_key),
            "has_openai_key": bool(config.llm.openai_api_key),
        },
    })


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
