"""
Phase 2: FeedbackRepository — record and retrieve user feedback on emails.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.database.models import Feedback


class FeedbackRepository:
    def record(
        self,
        session: Session,
        *,
        email_id: uuid.UUID,
        feedback_type: str,
    ) -> Feedback:
        """Record a feedback event for an email."""
        fb = Feedback(
            id=uuid.uuid4(),
            email_message_id=email_id,
            feedback_type=feedback_type,
        )
        session.add(fb)
        session.flush()
        return fb

    def for_email(self, session: Session, email_id: uuid.UUID) -> list[Feedback]:
        return (
            session.query(Feedback)
            .filter_by(email_message_id=email_id)
            .order_by(Feedback.created_at.desc())
            .all()
        )

    def always_important_senders(self, session: Session, user_id: uuid.UUID) -> set[str]:
        from app.database.models import EmailMessage
        from app.email.parser import extract_email_address

        rows = (
            session.query(EmailMessage.sender)
            .join(Feedback, EmailMessage.id == Feedback.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                Feedback.feedback_type == "always_important"
            )
            .all()
        )
        return {extract_email_address(r[0]) for r in rows if r[0]}

    def ignored_senders(self, session: Session, user_id: uuid.UUID) -> set[str]:
        from app.database.models import EmailMessage
        from app.email.parser import extract_email_address

        rows = (
            session.query(EmailMessage.sender)
            .join(Feedback, EmailMessage.id == Feedback.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                Feedback.feedback_type == "ignore_sender"
            )
            .all()
        )
        return {extract_email_address(r[0]) for r in rows if r[0]}
