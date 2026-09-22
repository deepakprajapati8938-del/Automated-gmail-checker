"""
Command implementations. Each function returns the text to send — handlers.py
is responsible for auth + actually sending it.

Phase 2: functions accept either (session, user_id) for Postgres or (store,) for
Phase 1 SQLite, selected once at startup by main.py based on settings.uses_database().
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.database.models import EmailMessage

HELP_TEXT = """<b>Telegram AI Email Agent</b>

I watch your Gmail inbox and ping you here when something important shows up.

<b>Commands</b>
/inbox — recently important emails
/important — emails scored 7+
/today — emails received today
/deadlines — upcoming deadlines
/actions — emails that need action from you
/digest — summary of important emails in the last 24h
/settings — current configuration
/reset — clear conversation memory
/help — this message

<b>Natural language</b>
Just type a question like "what was the interview date?" and I'll search your emails.
"""

SETTINGS_TEXT = """<b>Settings</b>

Notification thresholds (fixed for now, personalization arrives in Phase 5):
  0–4  → no notification
  5–6  → daily digest
  7–8  → immediate notification
  9–10 → immediate + high priority
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_email(email: "EmailMessage") -> str:
    """Format a single EmailMessage ORM object as HTML."""
    a = email.analysis
    score = a.importance_score if a else 0
    summary = a.summary if a else ""
    return (
        f"<b>{email.subject}</b>\n"
        f"From: {email.sender}\n"
        f"Score: {score}/10 | Tier: {email.notification_tier}\n"
        f"{summary}"
    )


def _fmt_row(row: dict) -> str:
    """Format a dict (Phase 1 SQLite row) as HTML."""
    return (
        f"<b>{row['subject']}</b>\n"
        f"From: {row['sender']}\n"
        f"Score: {row['importance_score']}/10 | Tier: {row['notification_tier']}\n"
        f"{row['summary']}"
    )


# ---------------------------------------------------------------------------
# Phase 2: Postgres-backed commands
# ---------------------------------------------------------------------------

def inbox_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.emails import EmailRepository
    emails = EmailRepository().recent_notified(session, user_id, limit=10)
    if not emails:
        return "Nothing notified yet."
    return "<b>Recent inbox</b>\n\n" + "\n\n".join(_fmt_email(e) for e in emails)


def important_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.emails import EmailRepository
    emails = EmailRepository().important(session, user_id, min_score=7, limit=10)
    if not emails:
        return "No emails scored 7+ this session."
    return "<b>Important emails (7+)</b>\n\n" + "\n\n".join(_fmt_email(e) for e in emails)


def today_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.emails import EmailRepository
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    emails = EmailRepository().since(session, user_id, today, limit=15)
    if not emails:
        return "No emails received today."
    return "<b>Today's emails</b>\n\n" + "\n\n".join(_fmt_email(e) for e in emails)


def deadlines_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.emails import EmailRepository
    emails = EmailRepository().with_deadlines(session, user_id, limit=15)
    if not emails:
        return "No deadlines extracted yet. (Structured deadline tracking expands in Phase 4.)"
    lines = []
    for e in emails:
        dl = e.analysis.deadline if e.analysis else "?"
        lines.append(f"📅 {dl} — <b>{e.subject}</b>")
    return "<b>Upcoming deadlines</b>\n\n" + "\n".join(lines)


def actions_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.emails import EmailRepository
    emails = EmailRepository().requires_action(session, user_id, limit=15)
    if not emails:
        return "Nothing requiring action right now."
    return "<b>Needs your action</b>\n\n" + "\n\n".join(_fmt_email(e) for e in emails)


def digest_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.emails import EmailRepository
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    emails = EmailRepository().since(session, user_id, since, limit=50)
    emails = [e for e in emails if e.analysis and e.analysis.importance_score >= 5]
    if not emails:
        return "📬 DAILY EMAIL DIGEST\n\nNothing notable in the last 24 hours."
    emails.sort(key=lambda e: -(e.analysis.importance_score if e.analysis else 0))
    tier_emoji = {"immediate": "🔴", "notify": "🟠", "digest": "🟡"}
    lines = [f"You have {len(emails)} important emails in the last 24 hours.\n"]
    for e in emails[:10]:
        emoji = tier_emoji.get(e.notification_tier, "⚪")
        lines.append(f"{emoji} {e.subject}")
    return "📬 DAILY EMAIL DIGEST\n\n" + "\n".join(lines)


def why_important_text_pg(session: "Session", user_id: uuid.UUID, message_id: str) -> str:
    from app.database.repositories.emails import EmailRepository
    email = EmailRepository().get_by_message_id(session, message_id)
    if email is None:
        return "I don't have a record of that email."
    a = email.analysis
    if a is None:
        return f"<b>{email.subject}</b>\n\nNo AI analysis available (was filtered pre-AI)."
    return (
        f"<b>{email.subject}</b>\n\n"
        f"Importance: {a.importance_score}/10 ({a.urgency} urgency)\n"
        f"Category: {a.category}\n\n"
        f"{a.reason}"
    )


def settings_text_pg(session: "Session", user_id: uuid.UUID) -> str:
    from app.database.repositories.feedback import FeedbackRepository
    repo = FeedbackRepository()
    always_important = repo.always_important_senders(session, user_id)
    ignored = repo.ignored_senders(session, user_id) - always_important

    text = SETTINGS_TEXT + "\n<b>Personalization Rules</b>\n"
    
    if always_important:
        text += "\n<b>⭐ Always Important Senders:</b>\n"
        for sender in sorted(always_important):
            text += f"• {sender}\n"
    else:
        text += "\n<b>⭐ Always Important Senders:</b> (none)\n"
        
    if ignored:
        text += "\n<b>🔕 Ignored Senders:</b>\n"
        for sender in sorted(ignored):
            text += f"• {sender}\n"
    else:
        text += "\n<b>🔕 Ignored Senders:</b> (none)\n"
        
    return text

def metrics_text() -> str:
    from app.services import metrics
    snapshot = metrics.snapshot()
    if not snapshot:
        return "<b>Metrics</b>\n\nNo metrics recorded yet."
    
    text = "<b>Metrics</b>\n\n"
    for k, v in sorted(snapshot.items()):
        text += f"{k}: {v}\n"
    return text

# ---------------------------------------------------------------------------
# Phase 1: SQLite-backed commands (kept for fallback)
# ---------------------------------------------------------------------------

def inbox_text(store) -> str:
    rows = store.recent_notifications(only_notified=True, limit=10)
    if not rows:
        return "Nothing notified yet."
    return "<b>Recent inbox</b>\n\n" + "\n\n".join(_fmt_row(dict(r)) for r in rows)


def important_text(store) -> str:
    rows = [r for r in store.recent_notifications(limit=100) if r["importance_score"] >= 7]
    if not rows:
        return "No emails scored 7+ this session."
    return "<b>Important emails (7+)</b>\n\n" + "\n\n".join(_fmt_row(dict(r)) for r in rows[:10])


def today_text(store) -> str:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = [r for r in store.notifications_since(today)]
    if not rows:
        return "No emails received today."
    return "<b>Today's emails</b>\n\n" + "\n\n".join(_fmt_row(dict(r)) for r in rows[:15])


def deadlines_text(store) -> str:
    rows = [r for r in store.recent_notifications(limit=100) if r["deadline"]]
    if not rows:
        return "No deadlines extracted yet. (Structured deadline tracking expands in Phase 4.)"
    rows.sort(key=lambda r: r["deadline"])
    lines = [f"📅 {r['deadline']} — <b>{r['subject']}</b>" for r in rows[:15]]
    return "<b>Upcoming deadlines</b>\n\n" + "\n".join(lines)


def actions_text(store) -> str:
    rows = [r for r in store.recent_notifications(limit=100) if r["requires_action"]]
    if not rows:
        return "Nothing requiring action right now."
    return "<b>Needs your action</b>\n\n" + "\n\n".join(_fmt_row(dict(r)) for r in rows[:15])


def digest_text(store) -> str:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = [r for r in store.notifications_since(since) if r["importance_score"] >= 5]
    if not rows:
        return "📬 DAILY EMAIL DIGEST\n\nNothing notable in the last 24 hours."
    rows.sort(key=lambda r: -r["importance_score"])
    tier_emoji = {"immediate": "🔴", "notify": "🟠", "digest": "🟡"}
    lines = [f"You have {len(rows)} important emails in the last 24 hours.\n"]
    for r in rows[:10]:
        emoji = tier_emoji.get(r["notification_tier"], "⚪")
        lines.append(f"{emoji} {r['subject']}")
    return "📬 DAILY EMAIL DIGEST\n\n" + "\n".join(lines)


def why_important_text(store, message_id: str) -> str:
    row = store.get_notification(message_id)
    if row is None:
        return "I don't have a record of that email anymore."
    return (
        f"<b>{row['subject']}</b>\n\n"
        f"Importance: {row['importance_score']}/10 ({row['urgency']} urgency)\n"
        f"Category: {row['category']}\n\n"
        f"{row['reason']}"
    )
