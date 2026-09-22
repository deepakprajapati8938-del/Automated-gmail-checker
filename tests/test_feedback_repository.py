import uuid

import pytest

from app.database.models import User, EmailMessage, Feedback
from app.database.repositories.feedback import FeedbackRepository


@pytest.fixture
def mock_feedback_user(db_session):
    user = User(id=uuid.uuid4(), telegram_user_id=111, email_address="fb@example.com")
    db_session.add(user)

    def _make_msg(sender: str) -> uuid.UUID:
        msg_id = uuid.uuid4()
        msg = EmailMessage(
            id=msg_id,
            user_id=user.id,
            gmail_message_id=str(msg_id),
            thread_id=str(msg_id),
            subject="Test",
            sender=sender,
            notification_tier="notify",
        )
        db_session.add(msg)
        return msg_id

    # Sender 1: Alice (Always Important)
    alice_msg = _make_msg("Alice <alice@example.com>")
    db_session.add(Feedback(id=uuid.uuid4(), email_message_id=alice_msg, feedback_type="always_important"))

    # Sender 2: Bob (Ignore)
    bob_msg = _make_msg("bob@example.com")
    db_session.add(Feedback(id=uuid.uuid4(), email_message_id=bob_msg, feedback_type="ignore_sender"))

    # Sender 3: Charlie (Both: always important wins)
    charlie_msg1 = _make_msg("Charlie <charlie@example.com>")
    charlie_msg2 = _make_msg("Charlie <charlie@example.com>")
    db_session.add(Feedback(id=uuid.uuid4(), email_message_id=charlie_msg1, feedback_type="always_important"))
    db_session.add(Feedback(id=uuid.uuid4(), email_message_id=charlie_msg2, feedback_type="ignore_sender"))

    db_session.commit()
    return user.id


@pytest.mark.skip(reason="Requires DB")
def test_sender_preferences(db_session, mock_feedback_user):
    repo = FeedbackRepository()
    always_important = repo.always_important_senders(db_session, mock_feedback_user)
    ignored = repo.ignored_senders(db_session, mock_feedback_user) - always_important

    assert "alice@example.com" in always_important
    assert "charlie@example.com" in always_important
    assert "bob@example.com" not in always_important

    assert "bob@example.com" in ignored
    assert "alice@example.com" not in ignored
    assert "charlie@example.com" not in ignored  # Charlie is filtered out of ignored by the difference operation
