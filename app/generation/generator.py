"""Generation module with LiteLLM orchestration and offline fallback capabilities."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import typing
try:
    import typing_extensions
    if not hasattr(typing, "NotRequired"):
        typing.NotRequired = getattr(typing_extensions, "NotRequired", None)
    if not hasattr(typing, "Required"):
        typing.Required = getattr(typing_extensions, "Required", None)
except ImportError:
    pass

import litellm

# Pydantic 2.13+ compatibility workaround for LiteLLM
try:
    import pydantic
    from litellm.types import utils as litellm_utils
    if hasattr(litellm_utils, "Message"):
        if not hasattr(litellm_utils, "ChatCompletionReasoningSummaryTextBlock"):
            class ChatCompletionReasoningSummaryTextBlock(pydantic.BaseModel):
                pass
            setattr(litellm_utils, "ChatCompletionReasoningSummaryTextBlock", ChatCompletionReasoningSummaryTextBlock)
        if hasattr(litellm_utils.Message, "model_rebuild"):
            litellm_utils.Message.model_rebuild()
        if hasattr(litellm_utils, "Choices") and hasattr(litellm_utils.Choices, "model_rebuild"):
            litellm_utils.Choices.model_rebuild()
        if hasattr(litellm_utils, "ModelResponse") and hasattr(litellm_utils.ModelResponse, "model_rebuild"):
            litellm_utils.ModelResponse.model_rebuild()
except Exception:
    pass

from app.augmentation.prompt_builder import AugmentedPrompt, CitationInfo
from app.config import LLMConfig, config
from app.logging_config import logger

# Asset paths and loaders
_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_GENERATION_TEXTS_PATH = _ASSETS_DIR / "configs" / "generation_texts.json"
_NLP_STOPWORDS_PATH = _ASSETS_DIR / "configs" / "nlp_stopwords.json"


def _load_json_asset(path: Path) -> Dict[str, Any]:
    """Read and parse a JSON configuration asset file with fail-fast error handling."""
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


class GenerationError(Exception):
    """Raised when LLM completion fails."""
    pass


@dataclass
class GenerationResult:
    """Comprehensive output of the generation stage."""
    answer: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    citations: List[CitationInfo] = field(default_factory=list)
    is_refusal: bool = False
    is_offline_mode: bool = False
    raw_response: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 2),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "citations": [c.to_dict() for c in self.citations],
            "is_refusal": self.is_refusal,
            "is_offline_mode": self.is_offline_mode,
        }


class LLMGenerator:
    """
    Orchestrates LLM generation across providers (Gemini, OpenRouter, OpenAI) using LiteLLM,
    with an intelligent extractive fallback mode for offline/test environments.
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self.config = llm_config or config.llm
        # Configure litellm telemetry dynamically based on config
        litellm.suppress_debug_info = getattr(self.config, "suppress_debug_info", True)
        self._setup_api_keys()

    def _setup_api_keys(self) -> None:
        """Inject configured API keys into environment for LiteLLM resolution."""
        if self.config.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.config.gemini_api_key
        if self.config.openrouter_api_key:
            os.environ["OPENROUTER_API_KEY"] = self.config.openrouter_api_key
        if self.config.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.config.openai_api_key

    def _has_api_credentials(self, model: str) -> bool:
        """Check if required API credentials exist for the chosen model."""
        if model.lower().startswith("offline") or model.lower().startswith("mock"):
            return False

        if "gemini" in model.lower():
            return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        elif "openrouter" in model.lower():
            return bool(os.getenv("OPENROUTER_API_KEY"))
        elif "gpt" in model.lower() or "openai" in model.lower():
            return bool(os.getenv("OPENAI_API_KEY"))
        elif "ollama" in model.lower():
            return True

        # If any key is present, let litellm attempt
        return bool(
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

    def _generate_offline_response(
        self,
        prompt: AugmentedPrompt,
        start_time: float,
    ) -> GenerationResult:
        """
        Extractive offline generator for deterministic testing and key-less demonstration.
        Grounded strictly in retrieved context with keyword matching and refusal detection.
        """
        logger.info("Executing generation in offline/mock mode...")
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        refusal_text = DEFAULT_REFUSAL_TEXT

        if not prompt.citations_map or prompt.formatted_context == "[NO RELEVANT CONTEXT FOUND]":
            return GenerationResult(
                answer=refusal_text,
                model="offline-grounded-fallback",
                latency_ms=elapsed_ms,
                prompt_tokens=len(prompt.full_prompt_text) // 4,
                completion_tokens=len(refusal_text) // 4,
                total_tokens=(len(prompt.full_prompt_text) + len(refusal_text)) // 4,
                citations=[],
                is_refusal=True,
                is_offline_mode=True,
            )

        # Extract meaningful query keywords (words >= 3 chars, excluding common stop words)
        stopwords = STOPWORDS
        anchor_terms = ANCHOR_TERMS

        raw_query_words = [
            w.lower().strip("?,!.:;\"'()")
            for w in prompt.user_query.split()
            if len(w.strip("?,!.:;\"'()")) >= 3 and w.lower().strip("?,!.:;\"'()") not in stopwords
        ]
        topic_words = [w for w in raw_query_words if w not in anchor_terms]
        query_words = raw_query_words

        # Check if topic words exist anywhere in the combined context
        all_context_lower = prompt.formatted_context.lower()
        if topic_words:
            matched_topic_words = [tw for tw in topic_words if tw in all_context_lower]
            threshold = getattr(self.config, "offline_topic_threshold", 0.4)
            # If less than configured threshold of topic words exist in context, refuse
            if len(matched_topic_words) < max(1, len(topic_words) * threshold):
                return GenerationResult(
                    answer=refusal_text,
                    model="offline-grounded-fallback",
                    latency_ms=elapsed_ms,
                    prompt_tokens=len(prompt.full_prompt_text) // 4,
                    completion_tokens=len(refusal_text) // 4,
                    total_tokens=(len(prompt.full_prompt_text) + len(refusal_text)) // 4,
                    citations=[],
                    is_refusal=True,
                    is_offline_mode=True,
                )

        matched_sentences: List[str] = []
        cited_sources: List[CitationInfo] = []

        for idx, cit in prompt.citations_map.items():
            raw_sentences = [s.strip() for s in cit.snippet.replace("\n", " ").split(". ") if s.strip()]
            for sentence in raw_sentences:
                sent_lower = sentence.lower()
                match_count = sum(1 for qw in (topic_words or query_words) if qw in sent_lower)
                if match_count > 0:
                    clean_sent = sentence.rstrip(".") + "."
                    matched_sentences.append(f"{clean_sent} [Source {idx}: {cit.filename}]")
                    if cit not in cited_sources:
                        cited_sources.append(cit)

        # If no sentences contain any query terms, trigger refusal
        if not matched_sentences:
            return GenerationResult(
                answer=refusal_text,
                model="offline-grounded-fallback",
                latency_ms=elapsed_ms,
                prompt_tokens=len(prompt.full_prompt_text) // 4,
                completion_tokens=len(refusal_text) // 4,
                total_tokens=(len(prompt.full_prompt_text) + len(refusal_text)) // 4,
                citations=[],
                is_refusal=True,
                is_offline_mode=True,
            )

        # Build grounded response from matched sentences up to configured sentence limit
        max_sentences = getattr(self.config, "offline_max_sentences", 4)
        answer = " ".join(matched_sentences[:max_sentences])

        return GenerationResult(
            answer=answer,
            model="offline-grounded-fallback",
            latency_ms=elapsed_ms,
            prompt_tokens=len(prompt.full_prompt_text) // 4,
            completion_tokens=len(answer) // 4,
            total_tokens=(len(prompt.full_prompt_text) + len(answer)) // 4,
            citations=cited_sources,
            is_refusal=False,
            is_offline_mode=True,
        )

    def generate(
        self,
        prompt: AugmentedPrompt,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """
        Execute LLM completion using LiteLLM with automatic provider fallback.
        """
        target_model = model or self.config.model
        target_temp = temperature if temperature is not None else self.config.temperature
        target_max_tokens = max_tokens or self.config.max_tokens

        start_time = time.perf_counter()

        # If no credentials or model set to offline, use educational offline generator
        if not self._has_api_credentials(target_model):
            logger.info("No active API keys found for model '%s'. Using offline generator.", target_model)
            return self._generate_offline_response(prompt, start_time)

        messages = [
            {"role": "system", "content": prompt.system_instruction},
            {
                "role": "user",
                "content": f"RETRIEVED CONTEXT:\n{prompt.formatted_context}\n\nUSER QUESTION:\n{prompt.user_query}",
            },
        ]

        logger.info(
            "Calling LLM provider via LiteLLM: model=%s, temp=%.2f, max_tokens=%d",
            target_model,
            target_temp,
            target_max_tokens,
        )

        try:
            completion_kwargs = {
                "model": target_model,
                "messages": messages,
                "temperature": target_temp,
                "max_tokens": target_max_tokens,
            }
            if "ollama" in target_model.lower():
                completion_kwargs["api_base"] = (
                    self.config.ollama_api_base
                    or os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
                )

            response = litellm.completion(**completion_kwargs)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            choice = response.choices[0]
            answer_text = choice.message.content.strip()

            usage = getattr(response, "usage", None)
            prompt_tokens = usage.prompt_tokens if usage else len(prompt.full_prompt_text) // 4
            completion_tokens = usage.completion_tokens if usage else len(answer_text) // 4
            total_tokens = usage.total_tokens if usage else prompt_tokens + completion_tokens

            # Detect refusal pattern
            refusal_signatures = REFUSAL_SIGNATURES
            is_refusal = any(sig in answer_text.lower() for sig in refusal_signatures)

            # Match which sources were cited
            used_citations: List[CitationInfo] = []
            for idx, cit in prompt.citations_map.items():
                if f"[Source {idx}" in answer_text or f"[source {idx}" in answer_text.lower() or not is_refusal:
                    used_citations.append(cit)

            logger.info(
                "Generation completed in %.1fms (tokens: %d prompt + %d completion). Refusal: %s",
                elapsed_ms,
                prompt_tokens,
                completion_tokens,
                is_refusal,
            )

            return GenerationResult(
                answer=answer_text,
                model=target_model,
                latency_ms=elapsed_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                citations=used_citations,
                is_refusal=is_refusal,
                is_offline_mode=False,
                raw_response=response.to_dict() if hasattr(response, "to_dict") else None,
            )

        except Exception as err:
            logger.error("LiteLLM generation failed for model '%s': %s", target_model, err)
            # Fall back to offline grounded generator rather than crashing
            logger.warning("Falling back to local grounded generator due to provider exception.")
            fallback_res = self._generate_offline_response(prompt, start_time)
            fallback_res.answer += FALLBACK_PROVIDER_NOTE_TEMPLATE.format(error=str(err))
            return fallback_res

    def stream_generate(
        self,
        prompt: AugmentedPrompt,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """Stream generated text chunks."""
        target_model = model or self.config.model
        if not self._has_api_credentials(target_model):
            res = self._generate_offline_response(prompt, time.perf_counter())
            # Stream words with small yield
            for word in res.answer.split(" "):
                yield word + " "
            return

        messages = [
            {"role": "system", "content": prompt.system_instruction},
            {
                "role": "user",
                "content": f"RETRIEVED CONTEXT:\n{prompt.formatted_context}\n\nUSER QUESTION:\n{prompt.user_query}",
            },
        ]

        try:
            stream = litellm.completion(
                model=target_model,
                messages=messages,
                temperature=temperature or self.config.temperature,
                max_tokens=max_tokens or self.config.max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as err:
            logger.error("Streaming generation failed: %s", err)
            yield f"Generation failed: {err}"
