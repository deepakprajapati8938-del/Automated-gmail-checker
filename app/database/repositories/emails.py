"""
Phase 2: EmailRepository — idempotency check, save, and all query methods.
Single write path: save() writes email_messages + email_analysis + extracted_events.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.ai.schemas import EmailAnalysis
from app.database.models import EmailAnalysis as EmailAnalysisModel
from app.database.models import EmailMessage, ExtractedEvent
from app.email.parser import NormalizedEmail


class EmailRepository:
    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def has_processed(self, session: Session, gmail_message_id: str) -> bool:
        """Return True if this gmail_message_id has already been saved."""
        return (
            session.query(EmailMessage)
            .filter_by(gmail_message_id=gmail_message_id)
            .first()
            is not None
        )

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def save(
        self,
        session: Session,
        *,
        user_id: uuid.UUID,
        email: NormalizedEmail,
        analysis: Optional[EmailAnalysis],
        notification_tier: str,
        notified: bool,
        ai_provider_name: str,
    ) -> EmailMessage:
        """Persist an email and its analysis in one call. Returns the saved EmailMessage row."""
        msg = EmailMessage(
            id=uuid.uuid4(),
            user_id=user_id,
            gmail_message_id=email.message_id,
            thread_id=email.thread_id,
            subject=email.subject,
            sender=email.sender,
            received_at=email.received_at,
            notification_tier=notification_tier,
            notified=notified,
            ai_provider_name=ai_provider_name,
        )
        session.add(msg)
        session.flush()  # get msg.id

        if analysis is not None:
            ana = EmailAnalysisModel(
                id=uuid.uuid4(),
                email_message_id=msg.id,
                importance_score=analysis.importance_score,
                urgency=analysis.urgency,
                category=analysis.category,
                requires_action=analysis.requires_action,
                summary=analysis.summary,
                reason=analysis.reason,
                deadline=analysis.deadline,
                action_items=analysis.action_items,
                entities=analysis.entities,
                confidence=analysis.confidence,
            )
            session.add(ana)

            # Save deadline as an extracted event
            if analysis.deadline:
                event = ExtractedEvent(
                    id=uuid.uuid4(),
                    email_message_id=msg.id,
                    event_type=analysis.event_type if analysis.event_type else "deadline",
                    event_date=analysis.deadline,
                    description=analysis.summary[:200],
                )
                session.add(event)

        return msg

    # ------------------------------------------------------------------
    # Queries (all eager-load analysis via joinedload)
    # ------------------------------------------------------------------

    def _base_query(self, session: Session):
        return session.query(EmailMessage).options(joinedload(EmailMessage.analysis))

    def get_by_message_id(self, session: Session, gmail_message_id: str) -> Optional[EmailMessage]:
        return (
            self._base_query(session)
            .filter(EmailMessage.gmail_message_id == gmail_message_id)
            .first()
        )

    def get_by_thread_id(self, session: Session, thread_id: str) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .filter(EmailMessage.thread_id == thread_id)
            .order_by(EmailMessage.received_at.asc())
            .all()
        )

    def recent_notified(self, session: Session, user_id: uuid.UUID, limit: int = 20) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .filter(EmailMessage.user_id == user_id, EmailMessage.notified == True)
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def important(
        self, session: Session, user_id: uuid.UUID, min_score: int = 7, limit: int = 20
    ) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .join(EmailAnalysisModel, EmailMessage.id == EmailAnalysisModel.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                EmailAnalysisModel.importance_score >= min_score,
            )
            .order_by(EmailAnalysisModel.importance_score.desc())
            .limit(limit)
            .all()
        )

    def since(
        self, session: Session, user_id: uuid.UUID, since_dt: datetime, limit: int = 50
    ) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .filter(EmailMessage.user_id == user_id, EmailMessage.received_at >= since_dt)
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def with_deadlines(self, session: Session, user_id: uuid.UUID, limit: int = 20) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .join(EmailAnalysisModel, EmailMessage.id == EmailAnalysisModel.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                EmailAnalysisModel.deadline.isnot(None),
            )
            .order_by(EmailAnalysisModel.deadline.asc())
            .limit(limit)
            .all()
        )

    def requires_action(self, session: Session, user_id: uuid.UUID, limit: int = 20) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .join(EmailAnalysisModel, EmailMessage.id == EmailAnalysisModel.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                EmailAnalysisModel.requires_action == True,
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def keyword_search(
        self, session: Session, user_id: uuid.UUID, query: str, limit: int = 20
    ) -> list[EmailMessage]:
        """Basic full-text ILIKE search on subject + analysis summary."""
        pattern = f"%{query}%"
        return (
            self._base_query(session)
            .outerjoin(EmailAnalysisModel, EmailMessage.id == EmailAnalysisModel.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                (EmailMessage.subject.ilike(pattern)) | (EmailAnalysisModel.summary.ilike(pattern)),
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def by_sender(
        self, session: Session, user_id: uuid.UUID, sender_substr: str, limit: int = 20
    ) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .filter(
                EmailMessage.user_id == user_id,
                EmailMessage.sender.ilike(f"%{sender_substr}%"),
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def by_date_range(
        self,
        session: Session,
        user_id: uuid.UUID,
        start: datetime,
        end: datetime,
        limit: int = 50,
    ) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .filter(
                EmailMessage.user_id == user_id,
                EmailMessage.received_at >= start,
                EmailMessage.received_at <= end,
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def by_category(
        self, session: Session, user_id: uuid.UUID, category: str, limit: int = 20
    ) -> list[EmailMessage]:
        return (
            self._base_query(session)
            .join(EmailAnalysisModel, EmailMessage.id == EmailAnalysisModel.email_message_id)
            .filter(
                EmailMessage.user_id == user_id,
                EmailAnalysisModel.category == category.lower(),
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
            .all()
        )

    def filtered(
        self,
        session: Session,
        user_id: uuid.UUID,
        *,
        sender: Optional[str] = None,
        category: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[EmailMessage]:
        """Generic metadata pre-filter used by hybrid search."""
        q = self._base_query(session).filter(EmailMessage.user_id == user_id)
        if sender:
            q = q.filter(EmailMessage.sender.ilike(f"%{sender}%"))
        if category:
            q = q.join(EmailAnalysisModel, EmailMessage.id == EmailAnalysisModel.email_message_id).filter(
                EmailAnalysisModel.category == category.lower()
            )
        if start:
            q = q.filter(EmailMessage.received_at >= start)
        if end:
            q = q.filter(EmailMessage.received_at <= end)
        return q.order_by(EmailMessage.received_at.desc()).limit(limit).all()

    def find_stale_threads(
        self, session: Session, user_id: uuid.UUID, my_email_address: str, days: int
    ) -> list[EmailMessage]:
        """
        Finds distinct threads where the user's last message is older than `days`,
        no one else has replied, and we haven't already marked it followed up.
        """
        from datetime import timedelta, timezone
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=days)
        recent_threshold = now - timedelta(days=30)  # limit search to last 30 days

        # Get all distinct thread_ids touched by the user in the last 30 days
        thread_ids = session.query(EmailMessage.thread_id).filter(
            EmailMessage.user_id == user_id,
            EmailMessage.received_at >= recent_threshold,
        ).distinct().all()
        thread_ids = [t[0] for t in thread_ids]

        stale_threads = []
        for thread_id in thread_ids:
            messages = self.get_by_thread_id(session, thread_id)
            if not messages:
                continue

            # Check if this thread has already been nudged
            if any(m.followed_up_at is not None for m in messages):
                continue

            last_message = messages[-1]  # ordered by received_at asc
            if my_email_address.lower() in last_message.sender.lower():
                # Make naive if needed to compare
                dt = last_message.received_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < threshold:
                    stale_threads.append(last_message)

        return stale_threads

