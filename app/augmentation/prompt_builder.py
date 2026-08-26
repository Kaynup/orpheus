"""Augmentation module: transforms user queries and retrieved chunks into grounded, inspectable prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logging_config import logger
from app.retrieval.retriever import RetrievedChunk

# Asset paths
_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_SYSTEM_PROMPT_PATH = _ASSETS_DIR / "prompts" / "system-prompts" / "v1_system_instruction_001.txt"
_QUERY_TEMPLATE_PATH = _ASSETS_DIR / "prompts" / "full-prompt-templates" / "v1_user_query_template_001.txt"


def _load_asset(path: Path) -> str:
    """Read and return the stripped contents of a prompt asset file.

    Raises:
        FileNotFoundError: If the asset file does not exist at the expected path.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"Prompt asset file not found: {path}. Ensure the assets/prompts/ directory is present and the file exists."
        )
    return path.read_text(encoding="utf-8").strip()


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

    Loads the system instruction and user query template from versioned asset files at
    ``assets/prompts/``. Providing an explicit ``system_instruction`` overrides the file-based
    default (useful in tests or custom deployments).
    """

    def __init__(self, system_instruction: Optional[str] = None):
        self.system_instruction = system_instruction or _load_asset(_SYSTEM_PROMPT_PATH)
        self.query_template = _load_asset(_QUERY_TEMPLATE_PATH)

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

        user_content = self.query_template.format(
            formatted_context=formatted_context,
            query=query.strip(),
        )

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
