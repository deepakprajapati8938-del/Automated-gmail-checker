"""
Phase 3: EmailAgent — the tool-calling conversational loop.

Uses AIProvider.complete_structured() with AgentStep schema so ALL providers
(OpenAI, Gemini, Groq, local) work the same way — no provider-specific function
calling APIs used here.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.agents.prompts.agent import AGENT_SYSTEM_PROMPT
from app.agents.tools import TOOL_REGISTRY
from app.ai.base import AIProvider
from app.ai.schemas import AgentAnswer, AgentStep

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = "I couldn't find a reliable answer in your emails."


class EmailAgent:
    """Tool-calling agent that answers free-text questions about the user's inbox."""

    MAX_TOOL_HOPS = 4  # bounds worst-case cost/latency per question (spec §5, TELEGRAM_AGENT.md #5)

    def __init__(self, ai_provider: AIProvider, session: Session, user_id: uuid.UUID) -> None:
        self._ai_provider = ai_provider
        self._session = session
        self._user_id = user_id

    def answer(self, user_message: str, conversation_context: str = "") -> AgentAnswer:
        """Run the tool-calling loop and return a final answer.

        The loop:
          1. Build prompt from conversation context + current transcript.
          2. Ask LLM for the next AgentStep (structured JSON).
          3. If final_answer → return.
          4. If tool_call → execute tool, append result, loop.
          5. If MAX_TOOL_HOPS reached → return fallback (never invent).
        """
        transcript: list[str] = []
        if conversation_context:
            transcript.append(f"Conversation so far:\n{conversation_context}")
        transcript.append(f"User: {user_message}")

        for hop in range(self.MAX_TOOL_HOPS):
            user_prompt = "\n\n".join(transcript)
            try:
                step: AgentStep = self._ai_provider.complete_structured(
                    AGENT_SYSTEM_PROMPT,
                    user_prompt,
                    AgentStep,
                    max_tokens=800,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Agent LLM call failed on hop %d: %s", hop, exc)
                return AgentAnswer(text=FALLBACK_ANSWER, source_message_ids=[])

            logger.debug("Agent hop %d — thought: %s", hop, step.thought)

            if step.final_answer is not None:
                return AgentAnswer(
                    text=step.final_answer,
                    source_message_ids=step.sources,
                )

            if step.tool_call is None:
                # Neither tool_call nor final_answer set — treat as terminal fallback
                logger.warning("Agent hop %d: neither tool_call nor final_answer set.", hop)
                return AgentAnswer(text=FALLBACK_ANSWER, source_message_ids=[])

            tool_result = self._execute_tool(step.tool_call.tool_name, step.tool_call.arguments)
            tool_result_str = json.dumps(tool_result)[:4000]  # hard cap on context growth

            transcript.append(
                f"Tool call: {step.tool_call.tool_name}({json.dumps(step.tool_call.arguments)})"
            )
            transcript.append(f"Tool result: {tool_result_str}")

        # Hit MAX_TOOL_HOPS without a final answer — never invent one.
        logger.warning("Agent hit MAX_TOOL_HOPS=%d without a final answer.", self.MAX_TOOL_HOPS)
        return AgentAnswer(text=FALLBACK_ANSWER, source_message_ids=[])

    def _execute_tool(self, tool_name: str, arguments: dict) -> object:
        """Dispatch a tool call. Returns result or an error string (never raises)."""
        fn = TOOL_REGISTRY.get(tool_name)
        if fn is None:
            logger.warning("Agent called unknown tool: %r", tool_name)
            return f"Error: unknown tool '{tool_name}'. Valid tools: {sorted(TOOL_REGISTRY)}"

        try:
            return fn(self._session, self._user_id, **arguments)  # type: ignore[call-arg]
        except TypeError as exc:
            # Bad arguments from LLM
            logger.warning("Tool %r bad arguments %r: %s", tool_name, arguments, exc)
            return f"Error: bad arguments for tool '{tool_name}': {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.error("Tool %r raised: %s", tool_name, exc)
            return f"Error: {tool_name} failed: {exc}"
