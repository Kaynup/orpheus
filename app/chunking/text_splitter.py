"""Boundary-aware text chunking with full provenance metadata tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.chunking.tokenizer import estimate_tokens
from app.config import config
from app.ingestion.parser import ParsedDocument
from app.logging_config import logger


@dataclass
class TextChunk:
    """Represents a discrete text chunk derived from a document with full metadata."""

    chunk_id: str
    chunk_index: int
    content: str
    doc_id: str
    source_filename: str
    page_number: int
    start_char: int
    end_char: int
    token_count_estimate: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk into a dictionary suitable for serialization/Chroma storage."""
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "doc_id": self.doc_id,
            "source_filename": self.source_filename,
            "page_number": self.page_number,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "token_count_estimate": self.token_count_estimate,
            **self.metadata,
        }


class RecursiveTextSplitter:
    """
    Splits text recursively by natural boundaries:
    Double newlines (paragraphs) -> Single newlines -> Sentences (. ! ?) -> Words (spaces).
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        separators: Optional[List[str]] = None,
    ):
        self.chunk_size = chunk_size or config.chunk.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else config.chunk.chunk_overlap

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be strictly less than chunk_size ({self.chunk_size})"
            )

        self.separators = separators if separators is not None else config.chunk.separators

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text by separators until pieces fit within chunk_size."""
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)

        good_splits: List[str] = []
        for s in splits:
            if not s:
                continue
            if len(s) < self.chunk_size:
                good_splits.append(s)
            else:
                if new_separators:
                    sub_splits = self._split_text(s, new_separators)
                    good_splits.extend(sub_splits)
                else:
                    # Hard slice if no more separators exist
                    for j in range(0, len(s), self.chunk_size - self.chunk_overlap):
                        good_splits.append(s[j : j + self.chunk_size])

        # Merge splits with overlap
        current_chunk: List[str] = []
        current_len = 0

        for piece in good_splits:
            piece_len = len(piece) + (len(separator) if current_chunk else 0)
            if current_len + piece_len > self.chunk_size and current_chunk:
                merged = separator.join(current_chunk).strip()
                if merged:
                    final_chunks.append(merged)
                # Keep overlap items
                while current_chunk and current_len > self.chunk_overlap:
                    removed = current_chunk.pop(0)
                    current_len -= len(removed) + len(separator)

            current_chunk.append(piece)
            current_len += piece_len

        if current_chunk:
            merged = separator.join(current_chunk).strip()
            if merged:
                final_chunks.append(merged)

        return final_chunks

    def chunk_document(
        self,
        document: ParsedDocument,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> List[TextChunk]:
        """
        Split a parsed document into structured TextChunks with metadata and provenance.
        """
        active_chunk_size = chunk_size or self.chunk_size
        active_chunk_overlap = chunk_overlap if chunk_overlap is not None else self.chunk_overlap

        if active_chunk_size != self.chunk_size or active_chunk_overlap != self.chunk_overlap:
            splitter = RecursiveTextSplitter(
                chunk_size=active_chunk_size,
                chunk_overlap=active_chunk_overlap,
                separators=self.separators,
            )
        else:
            splitter = self

        logger.info(
            "Chunking document '%s' (size=%d, overlap=%d, pages=%d)...",
            document.filename,
            active_chunk_size,
            active_chunk_overlap,
            len(document.pages),
        )

        all_chunks: List[TextChunk] = []
        global_index = 0

        for page in document.pages:
            page_text = page.text.strip()
            if not page_text:
                continue

            raw_pieces = splitter._split_text(page_text, splitter.separators)

            current_pos = 0
            for piece in raw_pieces:
                piece_clean = piece.strip()
                if not piece_clean:
                    continue

                start_char = page_text.find(piece_clean, current_pos)
                if start_char == -1:
                    start_char = current_pos
                end_char = start_char + len(piece_clean)
                current_pos = max(0, end_char - active_chunk_overlap)

                chunk_id = f"{document.doc_id}_chunk_{global_index}"
                chunk = TextChunk(
                    chunk_id=chunk_id,
                    chunk_index=global_index,
                    content=piece_clean,
                    doc_id=document.doc_id,
                    source_filename=document.filename,
                    page_number=page.page_number,
                    start_char=start_char,
                    end_char=end_char,
                    token_count_estimate=estimate_tokens(piece_clean),
                    metadata={
                        "file_type": document.file_type,
                        "doc_checksum": document.checksum,
                    },
                )
                all_chunks.append(chunk)
                global_index += 1

        logger.info(
            "Created %d chunks for document '%s' (total chars: %d, estimated tokens: %d)",
            len(all_chunks),
            document.filename,
            sum(len(c.content) for c in all_chunks),
            sum(c.token_count_estimate for c in all_chunks),
        )
        return all_chunks
