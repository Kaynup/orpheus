"""Token estimation and processing utilities.

This module encapsulates token counting logic to decouple it from chunking and generation.
Currently uses a simple character-count heuristic, but serves as an architectural seam
for future integration with libraries like tiktoken or HuggingFace tokenizers.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of LLM tokens in a string using a fast heuristic.

    Uses the standard `len(text) // 4` rule of thumb for English text.
    Always returns at least 1 token if the input string is not empty.

    Args:
        text: The string to analyze.

    Returns:
        The estimated token count.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)
