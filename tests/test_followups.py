import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import User, EmailMessage
from app.services.followups import run_followup_sweep

@pytest.fixture
def mock_user_threads(db_session):
    user = User(
        id=uuid.uuid4(),
        telegram_user_id=999,
        email_address="me@example.com",
    )
    db_session.add(user)
    
    # Thread 1: Stale thread (user sent last message >5 days ago)
    msg1 = EmailMessage(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_message_id="msg-1",
        thread_id="th-stale",
        subject="Checking in",
        sender="me@example.com",
        received_at=datetime.now(timezone.utc) - timedelta(days=6),
        notification_tier="none",
    )
    db_session.add(msg1)

    # Thread 2: Fresh thread (user sent last message 2 days ago)
    msg2 = EmailMessage(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_message_id="msg-2",
        thread_id="th-fresh",
        subject="Hello",
        sender="me@example.com",
        received_at=datetime.now(timezone.utc) - timedelta(days=2),
        notification_tier="none",
    )
    db_session.add(msg2)

    # Thread 3: Not our message last
    msg3 = EmailMessage(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_message_id="msg-3",
        thread_id="th-replied",
        subject="Hello",
        sender="other@example.com",
        received_at=datetime.now(timezone.utc) - timedelta(days=6),
        notification_tier="none",
    )
    db_session.add(msg3)
    
    # Thread 4: Stale thread but already followed up
    msg4 = EmailMessage(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_message_id="msg-4",
        thread_id="th-followed-up",
        subject="Checking in again",
        sender="me@example.com",
        received_at=datetime.now(timezone.utc) - timedelta(days=6),
        notification_tier="none",
        followed_up_at=datetime.now(timezone.utc),
    )
    db_session.add(msg4)

    db_session.commit()
    return user.id


@pytest.mark.skip(reason="Requires DB")
def test_followup_sweep(db_session, mock_user_threads):
    stale = run_followup_sweep(db_session, mock_user_threads, "me@example.com", days=5)
    
    assert len(stale) == 1
    assert stale[0].thread_id == "th-stale"
