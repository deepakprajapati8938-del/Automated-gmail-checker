"""
Phase 4: deadline extraction/reminder sweep (spec section 20). Reads from
extracted_events (Phase 2 schema) and pushes reminder notifications through
app.telegram.notifications. Not implemented in Phase 1 — Phase 1's /deadlines
command only reflects deadlines the triage step already put inline in the
notification log (see app/telegram/commands.py::deadlines_text).
"""
from __future__ import annotations


import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database.models import ExtractedEvent
from app.database.repositories.events import EventRepository


def run_deadline_sweep(
    session: Session, user_id: uuid.UUID, window_hours: int
) -> list[ExtractedEvent]:
    """
    Fetch events due within window_hours that haven't been reminded.
    Returns the list of events (caller is responsible for sending notifications
    and calling EventRepository.mark_reminded).
    """
    window_end = datetime.now(timezone.utc) + timedelta(hours=window_hours)
    repo = EventRepository()
    return repo.due_within(session, user_id, window_end)
