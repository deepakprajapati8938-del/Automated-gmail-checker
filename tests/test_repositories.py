import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone

from app.database.models import User
from app.database.repositories.emails import EmailRepository
from app.email.parser import NormalizedEmail
from app.ai.schemas import EmailAnalysis

@pytest.fixture
def test_user(db_session):
    user = User(id=uuid.uuid4(), telegram_user_id=888, email_address="repo_test@example.com")
    db_session.add(user)
    db_session.commit()
    return user.id

@pytest.mark.skip(reason="Requires DB")
def test_duplicate_email_save_raises_integrity_error(db_session, test_user):
    repo = EmailRepository()
    
    email = NormalizedEmail(
        message_id="msg-123",
        thread_id="thread-123",
        sender="bob@example.com",
        recipients=["me@example.com"],
        cc=[],
        subject="Hello",
        body_text="Test body",
        snippet="Test...",
        received_at=datetime.now(timezone.utc),
        labels=[],
        has_attachments=False
    )
    
    analysis = EmailAnalysis(
        importance_score=5,
        urgency="low",
        category="other",
        requires_action=False,
        summary="Test summary",
        reason="Test reason",
        deadline=None,
        action_items=[],
        entities=[],
        confidence=0.9
    )
    
    # First save should succeed
    repo.save(db_session, test_user, email, analysis, "digest", False, "test_provider")
    db_session.commit()
    
    # Second save with same message_id should raise IntegrityError
    with pytest.raises(IntegrityError):
        repo.save(db_session, test_user, email, analysis, "digest", False, "test_provider")
        db_session.commit()
