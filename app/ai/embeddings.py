"""
Phase 2: Embedding generation — provider-abstracted, separate from AI triage.

EMBEDDING_PROVIDER can differ from AI_PROVIDER. Only "openai" and "gemini"
are supported (groq/local don't have embeddings APIs in this project).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return a vector embedding for the given text."""
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(input=[text], model=self._model)
        return response.data[0].embedding


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "models/text-embedding-004") -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = model

    def embed(self, text: str) -> list[float]:
        import google.generativeai as genai

        result = genai.embed_content(model=self._model, content=text)
        return result["embedding"]


def get_embedding_provider() -> EmbeddingProvider:
    """Factory: select the embedding provider from settings."""
    from app.config import settings

    provider = settings.embedding_provider
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
        )
    if provider == "gemini":
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.embedding_model or "models/text-embedding-004",
        )
    raise ValueError(
        f"Unknown embedding provider: {provider!r}. Must be 'openai' or 'gemini'."
    )
