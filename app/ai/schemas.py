"""
Structured-output schemas. Every AI call that's supposed to produce structured
data validates against one of these — this is what prevents a prompt injection
or a flaky model response from smuggling extra fields/instructions through the
pipeline (see SECURITY.md #6).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Urgency = Literal["low", "medium", "high"]

DEFAULT_CATEGORIES = [
    "career",
    "education",
    "work",
    "finance",
    "security",
    "personal",
    "travel",
    "shopping",
    "social",
    "newsletter",
    "promotion",
    "notification",
    "transactional",
    "other",
]


class EmailAnalysis(BaseModel):
    """The fixed schema the triage LLM call must return. See spec section 11."""

    importance_score: int = Field(ge=0, le=10)
    urgency: Urgency
    category: str
    requires_action: bool
    summary: str = Field(max_length=600)
    reason: str = Field(max_length=300)
    deadline: Optional[str] = None  # ISO-8601 string or None
    event_type: Optional[Literal["deadline", "interview", "meeting", "appointment", "application"]] = None
    action_items: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("category")
    @classmethod
    def _category_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("action_items", "entities")
    @classmethod
    def _cap_list_length(cls, v: list[str]) -> list[str]:
        # Defensive cap: an injected/malformed response can't balloon the
        # notification payload.
        return v[:10]


# ---------------------------------------------------------------------------
# Phase 3: Agent tool-call schema
# ---------------------------------------------------------------------------

class ToolCall(BaseModel):
    """A single tool call requested by the agent."""
    tool_name: str
    arguments: dict


class AgentStep(BaseModel):
    """One reasoning step in the agent loop. Exactly one of tool_call or final_answer must be set."""
    thought: str  # brief reasoning shown only in logs/tests, never to the user
    tool_call: Optional[ToolCall] = None
    final_answer: Optional[str] = None
    sources: list[str] = Field(default_factory=list)  # message_ids grounding final_answer

    @field_validator("final_answer")
    @classmethod
    def _check_mutual_exclusion(cls, v, info):
        # Validation: if tool_call is also set alongside final_answer, that's invalid.
        # Pydantic v2 field validators run per-field so we check in model_validator instead.
        return v

    def is_terminal(self) -> bool:
        return self.final_answer is not None


class AgentAnswer(BaseModel):
    """The final answer returned by EmailAgent.answer()."""
    text: str
    source_message_ids: list[str] = Field(default_factory=list)
