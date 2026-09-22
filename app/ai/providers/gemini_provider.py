from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider, AIProviderError
from app.ai.providers._shared import parse_structured_response, structured_prompt

T = TypeVar("T", bound=BaseModel)


class GeminiProvider(AIProvider):
    """Uses the current `google-genai` SDK (the old `google-generativeai`
    package is deprecated and no longer receives updates)."""

    def __init__(self, api_key: str, model: str):
        from google import genai  # local import

        self._client = genai.Client(api_key=api_key)
        self._model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def complete(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 1024) -> str:
        from google.genai import types

        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                ),
            )
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"Gemini completion failed: {exc}") from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def complete_structured(
        self, system_prompt: str, user_prompt: str, schema: Type[T], *, max_tokens: int = 1024
    ) -> T:
        from google.genai import types

        prompt = structured_prompt(schema, user_prompt)
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )
            raw = resp.text or ""
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"Gemini structured completion failed: {exc}") from exc
        return parse_structured_response(raw, schema)
