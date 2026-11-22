"""Free-tier LLM routing: Gemini Flash-Lite (default) -> Groq gpt-oss-120b fallback, or a mock."""
from __future__ import annotations

import os
from typing import Any

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def mock_enabled() -> bool:
    return os.getenv("MOCK_LLM", "false").lower() in ("1", "true", "yes")


def provider_order() -> list[str]:
    """Primary provider first, then the other as automatic 429 fallback."""
    primary = os.getenv("LLM_PROVIDER", "gemini").lower()
    if primary not in ("gemini", "groq"):
        raise ValueError("LLM_PROVIDER must be 'gemini' or 'groq'")
    other = "groq" if primary == "gemini" else "gemini"
    order = [primary]
    if os.getenv(f"{other.upper()}_API_KEY"):
        order.append(other)
    return order


def build_model(provider: str) -> Any:
    """Return an Agno model instance for the provider."""
    if provider == "gemini":
        from agno.models.google import Gemini
        return Gemini(id=GEMINI_MODEL, api_key=os.getenv("GEMINI_API_KEY"))
    if provider == "groq":
        from agno.models.groq import Groq
        return Groq(id=GROQ_MODEL, api_key=os.getenv("GROQ_API_KEY"))
    raise ValueError(f"unknown provider {provider}")


def raise_if_error_content(content: Any) -> Any:
    """Agno returns provider failures as an error-JSON string in `.content` instead of raising; surface them."""
    if isinstance(content, str):
        head = content.lstrip()[:200].lower()
        if head.startswith("{") and '"error"' in head:
            raise RuntimeError(content.strip()[:600])
    return content


def is_rate_limit(exc: BaseException) -> bool:
    """True for errors worth failing over on: HTTP 429 and transient provider overload / 5xx."""
    text = f"{type(exc).__name__} {exc}".lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    markers = ("429", "rate limit", "resource_exhausted", "503", "unavailable", "overloaded",
               "high demand", "502", "504", "timed out", "timeout")
    return any(m in text for m in markers)


def active_engine_label() -> str:
    if mock_enabled():
        return "MOCK (deterministic)"
    try:
        p = provider_order()[0]
    except ValueError:
        return "unconfigured"
    return f"Gemini {GEMINI_MODEL}" if p == "gemini" else f"Groq {GROQ_MODEL}"
