"""Shared generation asset constants loaded from JSON config files.

All modules in ``app.generation`` that need text constants (refusal strings,
stopwords, anchor terms) should import from here to avoid circular imports
and to keep constants in one place.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_GENERATION_TEXTS_PATH = _ASSETS_DIR / "configs" / "generation_texts.json"
_NLP_STOPWORDS_PATH = _ASSETS_DIR / "configs" / "nlp_stopwords.json"


def _load_json_asset(path: Path) -> Dict[str, Any]:
    """Read and parse a JSON configuration asset file."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Configuration asset file not found: {path}. "
            "Ensure the assets/configs/ directory is present and contains required JSON assets."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_GEN_TEXTS = _load_json_asset(_GENERATION_TEXTS_PATH)
_NLP_DATA = _load_json_asset(_NLP_STOPWORDS_PATH)

DEFAULT_REFUSAL_TEXT: str = _GEN_TEXTS["standard_refusal"]
FALLBACK_PROVIDER_NOTE_TEMPLATE: str = _GEN_TEXTS["fallback_provider_note"]
REFUSAL_SIGNATURES: List[str] = _GEN_TEXTS["refusal_signatures"]
STOPWORDS: set[str] = set(_NLP_DATA["stopwords"])
ANCHOR_TERMS: set[str] = set(_NLP_DATA["anchor_terms"])
