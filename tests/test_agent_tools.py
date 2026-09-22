from unittest.mock import MagicMock, patch
import uuid
import datetime

from app.database.models import EmailMessage, EmailAnalysis
from app.agents import tools

def test_serialize():
    user_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    email = EmailMessage(
        id=msg_id,
        user_id=user_id,
        gmail_message_id="msg123",
        thread_id="th123",
        subject="Hello",
        sender="foo@bar.com",
        received_at=datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc),
        notification_tier="important",
    )
    analysis = EmailAnalysis(
        email_message_id=msg_id,
        summary="A summary",
        reason="A reason",
        importance_score=8,
        urgency="high",
        category="career",
        requires_action=True,
        deadline=datetime.date(2026, 1, 2),
        action_items=["Do something"],
        entities=["Foo", "Bar"],
    )
    email.analysis = analysis

    serialized = tools._serialize(email)
    
    assert serialized["message_id"] == "msg123"
    assert serialized["subject"] == "Hello"
    assert serialized["summary"] == "A summary"
    assert serialized["importance_score"] == 8
    assert "body_text" not in serialized

    serialized_with_body = tools._serialize(email, include_body=True)
    assert serialized_with_body["body_text"] is None


@patch("app.agents.tools._email_repo")
def test_get_email(mock_repo):
    user_id = uuid.uuid4()
    email = EmailMessage(
        id=uuid.uuid4(),
        user_id=user_id,
        gmail_message_id="msg123",
        subject="Hello",
    )
    email.analysis = None
    mock_repo.get_by_message_id.return_value = email

    session = MagicMock()
    result = tools.get_email(session, user_id, "msg123")
    assert result is not None
    assert result["message_id"] == "msg123"
    assert "body_text" in result


@patch("app.agents.tools.hybrid_search")
def test_search_emails(mock_search):
    user_id = uuid.uuid4()
    email = EmailMessage(
        id=uuid.uuid4(),
        user_id=user_id,
        gmail_message_id="msg123",
        subject="Hello Search",
    )
    email.analysis = None
    mock_search.return_value = [email]

    session = MagicMock()
    results = tools.search_emails(session, user_id, "search query")
    
    assert len(results) == 1
    assert results[0]["subject"] == "Hello Search"
    assert mock_search.called
