from __future__ import annotations

import json
import logging
from typing import Any

from litellm import completion

logger = logging.getLogger(__name__)


class LLMSummarizer:
    """Summarize sanitized fare JSON only."""

    def __init__(self, ollama_model: str) -> None:
        self.models = [
            "gemini/gemini-1.5-flash",
            "groq/llama-3.1-8b-instant",
            ollama_model,
        ]

    def summarize(self, sanitized_fares: list[dict[str, Any]]) -> str:
        payload = json.dumps(sanitized_fares, sort_keys=True)
        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize sanitized travel fare JSON. "
                    "Do not request credentials, cookies, raw HTML, or private account data."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize availability, cheapest fare, and notable tradeoffs:\n{payload}",
            },
        ]

        last_error: Exception | None = None
        for model in self.models:
            try:
                logger.info("Requesting LLM summary with model %s", model)
                response = completion(model=model, messages=messages)
                content = response.choices[0].message.content
                return str(content)
            except Exception as exc:  # LiteLLM raises provider-specific exceptions.
                logger.warning("LLM model %s failed: %s", model, exc)
                last_error = exc

        raise RuntimeError("All LLM fallback models failed") from last_error
