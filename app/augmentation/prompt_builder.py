"""Augmentation module: transforms user queries and retrieved chunks into grounded, inspectable prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.logging_config import logger
from app.retrieval.retriever import RetrievedChunk


SYSTEM_INSTRUCTION = """You are Doc-QA Assistant, an accurate, grounded GenAI document assistant.

YOUR STRICT RULES:
1. Answer the user's question ONLY using the factual information provided in the RETRIEVED CONTEXT below.
2. CITATION REQUIREMENT: Every statement must cite its source using the format [Source N] (or [Source N, Page X] where page is available), matching the numbered sources in the context.
3. ANTI-HALLUCINATION GUARDRAIL: If the provided RETRIEVED CONTEXT does not contain sufficient facts to answer the question completely and accurately, or if the context is empty/irrelevant, you MUST state clearly:
   "I do not have sufficient information in the provided documents to answer this question."
4. Do NOT speculate, extrapolate, or use outside knowledge not present in the context.
5. Keep your tone professional, concise, and clear."""


@dataclass
class CitationInfo:
    """Metadata representing a specific cited source."""
    source_index: int
    filename: str
    page_number: int
    chunk_id: str
    similarity: float
    snippet: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_index": self.source_index,
            "filename": self.filename,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "similarity": round(self.similarity, 4),
            "snippet": self.snippet,
        }


@dataclass
class AugmentedPrompt:
    """Inspectable representation of the prompt prepared for the LLM generation layer."""
    system_instruction: str
    formatted_context: str
    user_query: str
    full_prompt_text: str
    citations_map: Dict[int, CitationInfo] = field(default_factory=dict)
    chunk_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_instruction": self.system_instruction,
            "formatted_context": self.formatted_context,
            "user_query": self.user_query,
            "full_prompt_text": self.full_prompt_text,
            "citations": [c.to_dict() for c in self.citations_map.values()],
            "chunk_count": self.chunk_count,
        }


class PromptBuilder:
    """
    Constructs grounded, citation-mapped prompts from retrieved document chunks and user queries.
    """

    def __init__(self, system_instruction: Optional[str] = None):
        self.system_instruction = system_instruction or SYSTEM_INSTRUCTION

    def build_prompt(
        self,
        query: str,
        retrieved_chunks: List[RetrievedChunk],
    ) -> AugmentedPrompt:
        """
        Format retrieved chunks into numbered source blocks and create an AugmentedPrompt.
        """
        citations_map: Dict[int, CitationInfo] = {}
        context_blocks: List[str] = []

        for idx, chunk in enumerate(retrieved_chunks, start=1):
            page_str = f"Page {chunk.page_number}" if chunk.page_number else "Page 1"
            header = f"--- [Source {idx}: {chunk.source_filename} ({page_str})] ---"
            body = chunk.content.strip()
            block = f"{header}\n{body}"
            context_blocks.append(block)

            # Record citation metadata for frontend/CLI citation pills
            citations_map[idx] = CitationInfo(
                source_index=idx,
                filename=chunk.source_filename,
                page_number=chunk.page_number,
                chunk_id=chunk.chunk_id,
                similarity=chunk.similarity,
                snippet=chunk.content.strip(),
            )

        if context_blocks:
            formatted_context = "\n\n".join(context_blocks)
        else:
            formatted_context = "[NO RELEVANT CONTEXT FOUND]"

        user_content = f"""RETRIEVED CONTEXT:
{formatted_context}

USER QUESTION:
{query.strip()}

GROUNDED ANSWER (with citations):"""

        full_prompt_text = f"{self.system_instruction}\n\n{user_content}"

        logger.debug(
            "Built augmented prompt for query '%s' with %d context sources (total context chars: %d)",
            query[:40],
            len(retrieved_chunks),
            len(formatted_context),
        )

        return AugmentedPrompt(
            system_instruction=self.system_instruction,
            formatted_context=formatted_context,
            user_query=query.strip(),
            full_prompt_text=full_prompt_text,
            citations_map=citations_map,
            chunk_count=len(retrieved_chunks),
        )
