from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider, AIProviderError
from app.ai.providers._shared import parse_structured_response, structured_prompt

T = TypeVar("T", bound=BaseModel)


class LocalOpenAICompatibleProvider(AIProvider):
    """
    Talks to any OpenAI-compatible local inference server (Ollama, LM Studio,
    vLLM's OpenAI shim, etc.) via the `openai` SDK pointed at a custom base_url.
    No API key is required for most local servers, so a dummy value is used.
    """

    def __init__(self, base_url: str, model: str):
        from openai import OpenAI  # local import

        self._client = OpenAI(api_key="local-not-required", base_url=base_url)
        self._model = model

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 1024) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"Local model completion failed: {exc}") from exc

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
    def complete_structured(
        self, system_prompt: str, user_prompt: str, schema: Type[T], *, max_tokens: int = 1024
    ) -> T:
        prompt = structured_prompt(schema, user_prompt)
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"Local model structured completion failed: {exc}") from exc
        return parse_structured_response(raw, schema)
