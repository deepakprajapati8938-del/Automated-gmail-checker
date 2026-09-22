import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import User, EmailMessage, ExtractedEvent
from app.services.deadlines import run_deadline_sweep
from app.database.repositories.events import EventRepository

@pytest.fixture
def mock_user_events(db_session):
    user = User(
        id=uuid.uuid4(),
        telegram_user_id=888,
        email_address="deadlines@example.com",
    )
    db_session.add(user)
    
    msg = EmailMessage(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_message_id="msg-1",
        thread_id="th-1",
        subject="Hello",
        sender="foo@bar.com",
        received_at=datetime.now(timezone.utc),
        notification_tier="important",
    )
    db_session.add(msg)
    
    # Event 1: Due in 2 hours
    event1 = ExtractedEvent(
        id=uuid.uuid4(),
        email_message_id=msg.id,
        event_type="deadline",
        event_date=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        description="Due soon",
    )
    db_session.add(event1)
    
    # Event 2: Due in 48 hours (outside 24h window)
    event2 = ExtractedEvent(
        id=uuid.uuid4(),
        email_message_id=msg.id,
        event_type="deadline",
        event_date=(datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(),
        description="Due later",
    )
    db_session.add(event2)
    
    # Event 3: Due in 1 hour but already reminded
    event3 = ExtractedEvent(
        id=uuid.uuid4(),
        email_message_id=msg.id,
        event_type="deadline",
        event_date=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        description="Due very soon but reminded",
        reminded_at=datetime.now(timezone.utc),
    )
    db_session.add(event3)
    
    db_session.commit()
    return user.id


@pytest.mark.skip(reason="Requires DB")
def test_deadline_sweep(db_session, mock_user_events):
    events = run_deadline_sweep(db_session, mock_user_events, window_hours=24)
    assert len(events) == 1
    assert events[0].description == "Due soon"

    # Mark as reminded
    repo = EventRepository()
    repo.mark_reminded(db_session, events[0].id)
    
    # Second sweep should return nothing
    events2 = run_deadline_sweep(db_session, mock_user_events, window_hours=24)
    assert len(events2) == 0
