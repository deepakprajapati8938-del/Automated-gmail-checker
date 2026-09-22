"""
Phase 3: Conversation memory — rolling ring buffer + summary for multi-turn context.

Uses telegram_conversations table (already in Phase 2 schema).
Also writes agent_messages as an audit log (separate from memory source).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.ai.base import AIProvider
from app.database.models import AgentMessage, TelegramConversation


class ConversationMemory:
    RING_BUFFER_SIZE = 6       # last N user+agent turn pairs kept verbatim
    RESUMMARIZE_EVERY = 6      # regenerate rolling summary every N new turns

    def get_context(self, session: Session, user_id: uuid.UUID) -> str:
        """Return formatted context string for injection into EmailAgent.answer()."""
        conv = self._load(session, user_id)
        if conv is None:
            return ""

        parts = []
        if conv.summary:
            parts.append(conv.summary)

        messages: list[dict] = conv.last_messages or []
        for msg in messages:
            role = "User" if msg.get("role") == "user" else "Bot"
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")

        return "\n\n".join(parts)

    def record_turn(
        self,
        session: Session,
        user_id: uuid.UUID,
        ai_provider: AIProvider,
        user_message: str,
        bot_answer: str,
    ) -> None:
        """Append a user+agent turn to the ring buffer and update the summary if needed."""
        conv = self._load(session, user_id)
        if conv is None:
            conv = TelegramConversation(
                id=uuid.uuid4(),
                user_id=user_id,
                summary="",
                last_messages=[],
            )
            session.add(conv)

        messages: list[dict] = list(conv.last_messages or [])

        # Count existing turns to know when to re-summarize
        turn_count = len([m for m in messages if m.get("role") == "user"])

        # Append new turn pair
        messages.append({"role": "user", "content": user_message})
        messages.append({"role": "agent", "content": bot_answer})

        # Trim to ring buffer (RING_BUFFER_SIZE pairs = 2*N messages)
        max_msgs = self.RING_BUFFER_SIZE * 2
        evicted = messages[:-max_msgs] if len(messages) > max_msgs else []
        messages = messages[-max_msgs:]

        # Re-summarize every RESUMMARIZE_EVERY turns
        new_turn_count = turn_count + 1
        if new_turn_count % self.RESUMMARIZE_EVERY == 0 and evicted:
            try:
                evicted_text = "\n".join(
                    f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content']}"
                    for m in evicted
                )
                context_for_summary = (
                    f"Previous summary: {conv.summary}\n\nConversation to summarize:\n{evicted_text}"
                    if conv.summary
                    else evicted_text
                )
                new_summary = ai_provider.complete(
                    "Summarize the following email assistant conversation in 2-3 sentences, "
                    "focusing on what questions were asked and what was found.",
                    context_for_summary,
                    max_tokens=200,
                )
                conv.summary = new_summary
            except Exception:  # noqa: BLE001
                pass  # Summary failure is non-fatal — keep old summary

        conv.last_messages = messages
        conv.updated_at = datetime.now(timezone.utc)

        # Write audit log entry (agent_messages) — separate from memory source
        session.add(AgentMessage(
            id=uuid.uuid4(),
            user_id=user_id,
            role="user",
            content=user_message,
        ))
        session.add(AgentMessage(
            id=uuid.uuid4(),
            user_id=user_id,
            role="agent",
            content=bot_answer,
        ))

    def clear(self, session: Session, user_id: uuid.UUID) -> None:
        """Delete the user's conversation memory (for /reset command)."""
        conv = self._load(session, user_id)
        if conv is not None:
            session.delete(conv)

    def _load(self, session: Session, user_id: uuid.UUID) -> TelegramConversation | None:
        return session.query(TelegramConversation).filter_by(user_id=user_id).first()
