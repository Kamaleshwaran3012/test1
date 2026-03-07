from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import APIStatusError, Groq


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = _BACKEND_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_FILE)
_client: Groq | None = None
DEFAULT_LLM_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant"
DEFAULT_GEMINI_MODEL = DEFAULT_LLM_MODEL


class GeminiQuotaExceededError(RuntimeError):
    """Raised when upstream LLM API returns quota/rate-limit exhaustion."""

LLMQuotaExceededError = GeminiQuotaExceededError


def _get_client() -> Groq:
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            f"Groq API key is not configured (checked GROQ_API_KEY in {_ENV_FILE})"
        )

    _client = Groq(api_key=api_key)
    return _client


def invoke_text(prompt: str, *, model: str, temperature: float = 0.0) -> str:
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
    except APIStatusError as exc:
        if getattr(exc, "status_code", None) == 429:
            raise GeminiQuotaExceededError(str(exc)) from exc
        raise

    choice = (response.choices or [None])[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""


def parse_json_dict(response_text: str) -> dict[str, Any]:
    text = (response_text or "").strip()
    if not text:
        raise ValueError("LLM response is empty")

    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        value = json.loads(text[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object, received {type(value).__name__}")
    return value
