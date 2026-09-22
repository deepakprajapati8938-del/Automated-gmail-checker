from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai.base import AIProvider, AIProviderError
from app.ai.providers._shared import parse_structured_response, structured_prompt

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI  # local import: keep SDK usage isolated here

        self._client = OpenAI(api_key=api_key)
        self._model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
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
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise AIProviderError(f"OpenAI completion failed: {exc}") from exc

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def complete_structured(
        self, system_prompt: str, user_prompt: str, schema: Type[T], *, max_tokens: int = 1024
    ) -> T:
        prompt = structured_prompt(schema, user_prompt)
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"OpenAI structured completion failed: {exc}") from exc
        return parse_structured_response(raw, schema)
