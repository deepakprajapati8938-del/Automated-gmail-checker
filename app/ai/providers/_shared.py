"""Shared helpers used by every concrete AIProvider implementation."""
from __future__ import annotations

import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.ai.base import AIProviderError

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def structured_prompt(schema: Type[BaseModel], user_prompt: str) -> str:
    """Append explicit JSON-only output instructions for models without a
    native structured-output mode."""
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    return (
        f"{user_prompt}\n\n"
        "Respond with ONLY a single JSON object matching this JSON Schema. "
        "No markdown fences, no commentary, no text before or after the JSON.\n"
        f"JSON Schema:\n{schema_json}"
    )


def parse_structured_response(raw_text: str, schema: Type[T]) -> T:
    """Best-effort extraction + validation of a JSON object from model output."""
    text = raw_text.strip()
    # Strip markdown code fences if the model added them anyway.
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    candidate = text
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise AIProviderError(f"Model did not return JSON: {raw_text[:200]!r}")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Could not parse JSON from model output: {exc}") from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise AIProviderError(f"Model output failed schema validation: {exc}") from exc
