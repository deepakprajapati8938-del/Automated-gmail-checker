"""
SQLAlchemy ORM models matching DATABASE.md's schema (Phase 2).

Tables: users, email_messages, email_analysis, email_embeddings,
        feedback, extracted_events, telegram_conversations, agent_messages.

EMBEDDING_DIM = 1536 — matches OpenAI text-embedding-3-small.
Uses pgvector's Vector type for the embedding column.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 1536


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    email_messages: Mapped[list["EmailMessage"]] = relationship("EmailMessage", back_populates="user")
    telegram_conversations: Mapped[list["TelegramConversation"]] = relationship(
        "TelegramConversation", back_populates="user"
    )


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (UniqueConstraint("gmail_message_id", name="uq_email_messages_gmail_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sender: Mapped[str] = mapped_column(Text, nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notification_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_provider_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    followed_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="email_messages")
    analysis: Mapped["EmailAnalysis | None"] = relationship(
        "EmailAnalysis", back_populates="email_message", uselist=False
    )
    embedding: Mapped["EmailEmbedding | None"] = relationship(
        "EmailEmbedding", back_populates="email_message", uselist=False
    )
    feedback: Mapped[list["Feedback"]] = relationship("Feedback", back_populates="email_message")
    extracted_events: Mapped[list["ExtractedEvent"]] = relationship(
        "ExtractedEvent", back_populates="email_message"
    )


class EmailAnalysis(Base):
    __tablename__ = "email_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), nullable=False, unique=True
    )
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    requires_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    deadline: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    entities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    email_message: Mapped["EmailMessage"] = relationship("EmailMessage", back_populates="analysis")


class EmailEmbedding(Base):
    __tablename__ = "email_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), nullable=False, unique=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    email_message: Mapped["EmailMessage"] = relationship("EmailMessage", back_populates="embedding")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), nullable=False
    )
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    email_message: Mapped["EmailMessage"] = relationship("EmailMessage", back_populates="feedback")


class ExtractedEvent(Base):
    __tablename__ = "extracted_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, default="deadline")
    event_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    email_message: Mapped["EmailMessage"] = relationship("EmailMessage", back_populates="extracted_events")


class TelegramConversation(Base):
    __tablename__ = "telegram_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="telegram_conversations")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "agent" | "tool"
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
