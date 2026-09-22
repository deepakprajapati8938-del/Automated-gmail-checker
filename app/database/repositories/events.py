import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.models import EmailMessage, ExtractedEvent


class EventRepository:
    def due_within(self, session: Session, user_id: uuid.UUID, window_end: datetime) -> list[ExtractedEvent]:
        """Fetch upcoming events for a user that haven't been reminded yet."""
        stmt = (
            select(ExtractedEvent)
            .join(EmailMessage)
            .where(
                EmailMessage.user_id == user_id,
                ExtractedEvent.reminded_at.is_(None),
                ExtractedEvent.event_date.is_not(None)
            )
        )
        events = session.scalars(stmt).all()
        
        # Filter in python to parse dates and check against window_end
        # since event_date is a Text field.
        due_events = []
        for event in events:
            try:
                # We expect the AI to provide ISO-8601 strings (e.g. YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
                event_dt = datetime.fromisoformat(event.event_date.replace("Z", "+00:00"))
                # Make aware if needed
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
                if event_dt <= window_end:
                    due_events.append(event)
            except (ValueError, TypeError):
                pass

        return due_events

    def mark_reminded(self, session: Session, event_id: uuid.UUID) -> None:
        """Mark an event as reminded."""
        stmt = (
            update(ExtractedEvent)
            .where(ExtractedEvent.id == event_id)
            .values(reminded_at=datetime.now(timezone.utc))
        )
        session.execute(stmt)

    def by_types(self, session: Session, user_id: uuid.UUID, event_types: list[str], limit: int = 5) -> list[ExtractedEvent]:
        """Fetch recent events of specific types for a user."""
        stmt = (
            select(ExtractedEvent)
            .join(EmailMessage)
            .where(
                EmailMessage.user_id == user_id,
                ExtractedEvent.event_type.in_(event_types)
            )
            .order_by(ExtractedEvent.created_at.desc())
            .limit(limit)
        )
        return list(session.scalars(stmt).all())
