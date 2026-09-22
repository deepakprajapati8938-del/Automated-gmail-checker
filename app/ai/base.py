"""
Provider-agnostic AI interface. Nothing outside app/ai/providers/* should ever
import an SDK (openai, google.generativeai, groq, ...) directly — everything
else in the app talks to `AIProvider`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIProviderError(RuntimeError):
    """Raised when the underlying provider call fails after retries."""


class AIProvider(ABC):
    """Abstract interface every concrete AI provider must implement."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 1024) -> str:
        """Free-form text completion. Used for conversational answers (Phase 3+)."""
        raise NotImplementedError

    @abstractmethod
    def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
        *,
        max_tokens: int = 1024,
    ) -> T:
        """
        Return a validated instance of `schema`. Implementations should ask the
        underlying model for JSON matching the schema and then validate with
        pydantic — never trust the raw model output as-is.
        """
        raise NotImplementedError


def get_provider() -> AIProvider:
    """Factory selecting the concrete provider based on Settings.ai_provider."""
    from app.config import settings

    if settings.ai_provider == "openai":
        from app.ai.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.ai_model)
    if settings.ai_provider == "gemini":
        from app.ai.providers.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.ai_model)
    if settings.ai_provider == "groq":
        from app.ai.providers.groq_provider import GroqProvider

        return GroqProvider(api_key=settings.groq_api_key, model=settings.ai_model)
    if settings.ai_provider == "local":
        from app.ai.providers.local_provider import LocalOpenAICompatibleProvider

        return LocalOpenAICompatibleProvider(
            base_url=settings.local_ai_base_url, model=settings.ai_model
        )
    raise ValueError(f"Unknown AI provider: {settings.ai_provider}")
