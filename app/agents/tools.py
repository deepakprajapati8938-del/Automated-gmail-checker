"""
Phase 3: Agent tools — plain Python functions that query email data and return
JSON-serializable dicts. These are the ONLY operations the LLM can call.

IMPORTANT: All tools are read-only. None of these write to the database.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import EmailMessage
from app.database.repositories.emails import EmailRepository
from app.retrieval.search import hybrid_search

_email_repo = EmailRepository()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize(email: EmailMessage, *, include_body: bool = False) -> dict:
    """Convert EmailMessage ORM object to a JSON-serializable dict.

    By default body_text is NOT included (spec section 25 cost rule). Only
    get_email / get_thread pass include_body=True since those are the tools
    the agent calls when it explicitly needs full content.
    """
    a = email.analysis
    result: dict = {
        "message_id": email.gmail_message_id,
        "thread_id": email.thread_id,
        "subject": email.subject,
        "sender": email.sender,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "notification_tier": email.notification_tier,
        "summary": a.summary if a else None,
        "reason": a.reason if a else None,
        "importance_score": a.importance_score if a else None,
        "urgency": a.urgency if a else None,
        "category": a.category if a else None,
        "requires_action": a.requires_action if a else None,
        "deadline": a.deadline if a else None,
        "action_items": a.action_items if a else [],
        "entities": a.entities if a else [],
    }
    if include_body:
        # body_text lives on NormalizedEmail, not EmailMessage ORM.
        # We don't persist body_text to the DB (cost + privacy). The agent
        # has the summary/reason for most queries; full body retrieval is
        # handled by re-fetching from Gmail if truly needed (Phase 4+).
        # For now, return None so the field is present but explicit.
        result["body_text"] = None
    return result


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def search_emails(session: Session, user_id: uuid.UUID, query: str, limit: int = 10) -> list[dict]:
    """Semantic + keyword hybrid search across all emails."""
    results = hybrid_search(session, user_id=user_id, query_text=query, limit=limit)
    return [_serialize(e) for e in results]


def search_threads(session: Session, user_id: uuid.UUID, thread_id: str) -> list[dict]:
    """Return all emails in a given Gmail thread, ordered oldest-first."""
    emails = _email_repo.get_by_thread_id(session, thread_id)
    return [_serialize(e) for e in emails]


def get_email(session: Session, user_id: uuid.UUID, message_id: str) -> Optional[dict]:
    """Return full metadata for a single email by gmail_message_id. Returns None if not found."""
    email = _email_repo.get_by_message_id(session, message_id)
    if email is None or email.user_id != user_id:
        return None
    return _serialize(email, include_body=True)


def get_thread(session: Session, user_id: uuid.UUID, thread_id: str) -> list[dict]:
    """Alias of search_threads — return all emails in a thread."""
    return search_threads(session, user_id, thread_id)


def search_by_sender(session: Session, user_id: uuid.UUID, sender: str, limit: int = 10) -> list[dict]:
    """Find emails from a sender matching the given substring."""
    emails = _email_repo.by_sender(session, user_id, sender, limit=limit)
    return [_serialize(e) for e in emails]


def search_by_date(
    session: Session,
    user_id: uuid.UUID,
    start_iso: str,
    end_iso: str,
    limit: int = 20,
) -> list[dict]:
    """Find emails received between start_iso and end_iso (ISO-8601 strings)."""
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    emails = _email_repo.by_date_range(session, user_id, start, end, limit=limit)
    return [_serialize(e) for e in emails]


def search_by_subject(session: Session, user_id: uuid.UUID, subject_query: str, limit: int = 10) -> list[dict]:
    """Keyword/semantic search focused on the subject line."""
    results = hybrid_search(session, user_id=user_id, query_text=subject_query, limit=limit)
    return [_serialize(e) for e in results]


def search_by_category(session: Session, user_id: uuid.UUID, category: str, limit: int = 10) -> list[dict]:
    """Find emails classified under a specific category (e.g. 'career', 'finance')."""
    emails = _email_repo.by_category(session, user_id, category, limit=limit)
    return [_serialize(e) for e in emails]


def find_deadlines(session: Session, user_id: uuid.UUID, limit: int = 20) -> list[dict]:
    """Return emails that have an extracted deadline date."""
    emails = _email_repo.with_deadlines(session, user_id, limit=limit)
    return [_serialize(e) for e in emails]


def find_action_items(session: Session, user_id: uuid.UUID, limit: int = 20) -> list[dict]:
    """Return emails that require action from the user."""
    emails = _email_repo.requires_action(session, user_id, limit=limit)
    return [_serialize(e) for e in emails]


def find_events(session: Session, user_id: uuid.UUID, limit: int = 20) -> list[dict]:
    """Return events extracted from emails."""
    from app.database.repositories.events import EventRepository
    repo = EventRepository()
    events = repo.by_types(session, user_id, ["interview", "meeting", "appointment", "application"], limit=limit)
    return [_serialize(e.email_message) for e in events]


def get_important_emails(session: Session, user_id: uuid.UUID, min_score: int = 7, limit: int = 10) -> list[dict]:
    """Return emails with importance_score >= min_score."""
    emails = _email_repo.important(session, user_id, min_score=min_score, limit=limit)
    return [_serialize(e) for e in emails]


def get_recent_emails(session: Session, user_id: uuid.UUID, limit: int = 10) -> list[dict]:
    """Return emails received in the last 7 days."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    emails = _email_repo.since(session, user_id, since, limit=limit)
    return [_serialize(e) for e in emails]


def get_email_summary(session: Session, user_id: uuid.UUID, message_id: str) -> Optional[dict]:
    """Lighter-weight variant of get_email — returns only subject/summary/reason/received_at."""
    email = _email_repo.get_by_message_id(session, message_id)
    if email is None or email.user_id != user_id:
        return None
    a = email.analysis
    return {
        "message_id": email.gmail_message_id,
        "subject": email.subject,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "summary": a.summary if a else None,
        "reason": a.reason if a else None,
    }


# ---------------------------------------------------------------------------
# Tool dispatch registry — the ONLY tools the agent may call.
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, object] = {
    "search_emails": search_emails,
    "search_threads": search_threads,
    "get_email": get_email,
    "get_thread": get_thread,
    "search_by_sender": search_by_sender,
    "search_by_date": search_by_date,
    "search_by_subject": search_by_subject,
    "search_by_category": search_by_category,
    "find_deadlines": find_deadlines,
    "find_action_items": find_action_items,
    "find_events": find_events,
    "get_important_emails": get_important_emails,
    "get_recent_emails": get_recent_emails,
    "get_email_summary": get_email_summary,
}
