"""Persistent ChromaDB vector store management with deduplication and metadata preservation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# Use pysqlite3 if system sqlite3 is older than 3.35.0
try:
    __import__("pysqlite3")
    import sys

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import chromadb
from chromadb.config import Settings

from app.chunking.text_splitter import TextChunk
from app.config import config
from app.embedding.embedder import EmbeddingManager
from app.logging_config import logger


class VectorStoreError(Exception):
    """Raised when vector database operations fail."""

    pass


class VectorStore:
    """
    Manages persistent ChromaDB vector storage, chunk insertion, deduplication, and semantic retrieval.
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_manager: Optional[EmbeddingManager] = None,
    ):
        self.persist_dir = persist_dir or config.storage.persist_dir
        self.collection_name = collection_name or config.storage.collection_name
        self.embedding_manager = embedding_manager or EmbeddingManager()

        # Ensure persistence directory exists
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

        logger.info(
            "Connecting to ChromaDB persistent client at: %s (Collection: %s)",
            self.persist_dir,
            self.collection_name,
        )

        try:
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False, is_persistent=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_manager.get_embedding_function(),
                metadata={"hnsw:space": self.embedding_manager.distance_metric},
            )
            logger.info("ChromaDB initialized. Current chunk count: %d", self._collection.count())
        except Exception as err:
            logger.error("Failed to initialize ChromaDB: %s", err)
            raise VectorStoreError(f"Failed to initialize ChromaDB vector store: {err}") from err

    def add_chunks(self, chunks: List[TextChunk], replace_existing: bool = True) -> int:
        """
        Store a list of TextChunks into the persistent vector database.
        If replace_existing is True, any existing chunks for the same document ID are purged first.
        """
        if not chunks:
            logger.warning("No chunks provided to add_chunks.")
            return 0

        doc_id = chunks[0].doc_id
        source_filename = chunks[0].source_filename

        try:
            # Check for existing document chunks and remove if needed for clean update
            existing = self._collection.get(where={"doc_id": doc_id})
            if existing and existing.get("ids"):
                existing_count = len(existing["ids"])
                if replace_existing:
                    logger.info(
                        "Document '%s' (id=%s) already indexed (%d chunks). Purging old chunks for clean update...",
                        source_filename,
                        doc_id[:8],
                        existing_count,
                    )
                    self._collection.delete(ids=existing["ids"])
                else:
                    logger.info(
                        "Document '%s' already indexed (%d chunks). Skipping re-insertion.",
                        source_filename,
                        existing_count,
                    )
                    return 0

            # Prepare batch for Chroma
            ids = [chunk.chunk_id for chunk in chunks]
            documents = [chunk.content for chunk in chunks]
            metadatas = [
                {
                    "doc_id": str(chunk.doc_id),
                    "source_filename": str(chunk.source_filename),
                    "chunk_index": int(chunk.chunk_index),
                    "page_number": int(chunk.page_number),
                    "start_char": int(chunk.start_char),
                    "end_char": int(chunk.end_char),
                    "token_count_estimate": int(chunk.token_count_estimate),
                    "file_type": str(chunk.metadata.get("file_type", "")),
                    "doc_checksum": str(chunk.metadata.get("doc_checksum", "")),
                }
                for chunk in chunks
            ]

            batch_size = getattr(config.storage, "batch_size", 1000)
            logger.info(
                "Persisting %d chunks into collection '%s' in batches of %d...",
                len(chunks),
                self.collection_name,
                batch_size,
            )

            for i in range(0, len(ids), batch_size):
                self._collection.add(
                    ids=ids[i : i + batch_size],
                    documents=documents[i : i + batch_size],
                    metadatas=metadatas[i : i + batch_size],
                )
            logger.info(
                "Successfully persisted %d chunks for '%s'. Total collection chunks now: %d",
                len(chunks),
                source_filename,
                self._collection.count(),
            )
            return len(chunks)

        except Exception as err:
            logger.error("Failed to store chunks in ChromaDB: %s", err)
            raise VectorStoreError(f"Failed to persist chunks to vector database: {err}") from err

    def search(
        self,
        query_text: str,
        top_k: int = 3,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity vector search for a query string.
        Returns a list of result dictionaries containing content, metadata, distance, and similarity.
        """
        if not query_text or not query_text.strip():
            logger.warning("Empty query passed to vector store search.")
            return []

        total_available = self._collection.count()
        if total_available == 0:
            logger.warning("Search requested on empty vector store collection.")
            return []

        n_results = min(top_k, total_available)
        logger.debug("Searching vector store for query '%.60s...' with top_k=%d", query_text, n_results)

        try:
            query_kwargs: Dict[str, Any] = {
                "query_texts": [query_text.strip()],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            results = self._collection.query(**query_kwargs)

            # Unpack results into a structured list of items
            formatted_results: List[Dict[str, Any]] = []

            ids = results.get("ids", [[]])[0]
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for rank, (chunk_id, doc_text, meta, distance) in enumerate(zip(ids, docs, metas, distances), start=1):
                # Metric-agnostic similarity conversion
                similarity_score = self.embedding_manager.distance_to_similarity(float(distance))

                formatted_results.append(
                    {
                        "rank": rank,
                        "chunk_id": chunk_id,
                        "content": doc_text,
                        "distance": float(distance),
                        "similarity": similarity_score,
                        "metadata": meta,
                        "doc_id": meta.get("doc_id", ""),
                        "source_filename": meta.get("source_filename", "unknown"),
                        "page_number": meta.get("page_number", 1),
                        "chunk_index": meta.get("chunk_index", 0),
                    }
                )

            logger.info(
                "Search for '%.50s' returned %d chunks (top similarity: %.3f, top distance: %.3f)",
                query_text,
                len(formatted_results),
                formatted_results[0]["similarity"] if formatted_results else 0.0,
                formatted_results[0]["distance"] if formatted_results else 0.0,
            )
            return formatted_results

        except Exception as err:
            logger.error("Vector search query failed: %s", err)
            raise VectorStoreError(f"Semantic search query failed: {err}") from err

    def list_documents(self) -> List[Dict[str, Any]]:
        """
        Return a summary list of all unique documents currently stored in the vector database.
        """
        try:
            all_records = self._collection.get(include=["metadatas"])
            metas = all_records.get("metadatas", [])

            docs_summary: Dict[str, Dict[str, Any]] = {}

            for m in metas:
                if not m:
                    continue
                doc_id = m.get("doc_id", "unknown")
                if doc_id not in docs_summary:
                    docs_summary[doc_id] = {
                        "doc_id": doc_id,
                        "filename": m.get("source_filename", "unnamed"),
                        "file_type": m.get("file_type", ""),
                        "chunk_count": 0,
                        "pages": set(),
                        "total_tokens_estimate": 0,
                    }
                docs_summary[doc_id]["chunk_count"] += 1
                docs_summary[doc_id]["pages"].add(m.get("page_number", 1))
                docs_summary[doc_id]["total_tokens_estimate"] += m.get("token_count_estimate", 0)

            # Convert sets to page counts
            result = []
            for doc in docs_summary.values():
                result.append(
                    {
                        "doc_id": doc["doc_id"],
                        "filename": doc["filename"],
                        "file_type": doc["file_type"],
                        "chunk_count": doc["chunk_count"],
                        "page_count": len(doc["pages"]),
                        "total_tokens_estimate": doc["total_tokens_estimate"],
                    }
                )

            result.sort(key=lambda x: x["filename"].lower())
            return result

        except Exception as err:
            logger.error("Failed to list indexed documents: %s", err)
            raise VectorStoreError(f"Could not list documents from vector store: {err}") from err

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks associated with a specific document ID."""
        try:
            records = self._collection.get(where={"doc_id": doc_id})
            ids_to_delete = records.get("ids", [])
            if ids_to_delete:
                self._collection.delete(ids=ids_to_delete)
                logger.info("Deleted %d chunks for doc_id=%s", len(ids_to_delete), doc_id[:8])
                return len(ids_to_delete)
            return 0
        except Exception as err:
            logger.error("Failed to delete document %s: %s", doc_id, err)
            raise VectorStoreError(f"Failed to delete document from vector store: {err}") from err

    def get_collection_stats(self) -> Dict[str, Any]:
        """Return overall collection statistics."""
        try:
            count = self._collection.count()
            docs = self.list_documents()
            return {
                "total_chunks": count,
                "total_documents": len(docs),
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "documents": docs,
            }
        except Exception as err:
            logger.error("Failed to get collection stats: %s", err)
            return {
                "total_chunks": 0,
                "total_documents": 0,
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "error": str(err),
            }

    def reset_collection(self) -> None:
        """Delete all vectors and re-create an empty collection."""
        try:
            logger.warning("Resetting vector store collection '%s'...", self.collection_name)
            self._client.delete_collection(name=self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_manager.get_embedding_function(),
                metadata={"hnsw:space": self.embedding_manager.distance_metric},
            )
            logger.info("Collection '%s' reset successfully.", self.collection_name)
        except Exception as err:
            logger.error("Failed to reset collection: %s", err)
            raise VectorStoreError(f"Failed to reset vector collection: {err}") from err
