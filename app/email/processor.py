"""
Orchestrates: raw Gmail message -> normalize -> idempotency check ->
deterministic pre-filter -> AI triage -> notification-tier decision ->
persist notification log -> (maybe) send Telegram notification.

Phase 2: uses Postgres repositories (EmailRepository, EmbeddingRepository)
when settings.uses_database() is True. Falls back to Phase 1 SQLite Store
otherwise, so Phase 1-only setups continue to work unmodified.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable, Optional

from app.ai.base import AIProvider
from app.email.gmail import GmailClient
from app.email.parser import normalize_gmail_message
from app.services import triage as triage_service

logger = logging.getLogger(__name__)

NotifyCallback = Callable[["ProcessedEmail"], None]


class ProcessedEmail:
    """Small bundle handed to the notifier so it doesn't need to know about
    NormalizedEmail/EmailAnalysis internals directly."""

    def __init__(self, email, analysis, notification_tier: str):
        self.email = email
        self.analysis = analysis
        self.notification_tier = notification_tier


class EmailProcessor:
    def __init__(
        self,
        gmail: GmailClient,
        ai_provider: AIProvider,
        on_notify: NotifyCallback,
        # Phase 2 args (optional — if omitted, falls back to Phase 1 SQLite)
        user_id: Optional[uuid.UUID] = None,
        email_repo=None,
        embedding_repo=None,
        session_factory=None,
        # Phase 1 fallback
        store=None,
    ):
        self._gmail = gmail
        self._ai_provider = ai_provider
        self._on_notify = on_notify
        # Phase 2 Postgres path
        self._user_id = user_id
        self._email_repo = email_repo
        self._embedding_repo = embedding_repo
        self._session_factory = session_factory
        # Phase 1 SQLite fallback
        self._store = store

    @property
    def _uses_database(self) -> bool:
        return self._session_factory is not None and self._email_repo is not None

    def _preferences(self, session, user_id) -> tuple[set[str], set[str]]:
        """Derive always-important / ignored sender sets from stored feedback.
        Phase 5 implementation."""
        from app.database.repositories.feedback import FeedbackRepository
        feedback_repo = FeedbackRepository()
        always_important = feedback_repo.always_important_senders(session, user_id)
        ignored = feedback_repo.ignored_senders(session, user_id) - always_important
        return always_important, ignored

    def run_poll_cycle(self) -> int:
        """Runs one full poll cycle. Returns the number of emails processed."""
        processed_count = 0
        
        always_important: set[str] = set()
        ignored: set[str] = set()
        if self._uses_database:
            from app.database.session import session_scope
            with session_scope() as session:
                always_important, ignored = self._preferences(session, self._user_id)

        for message_id in self._gmail.poll_new_message_ids():
            if self._is_processed(message_id):
                logger.debug("Message %s already processed, skipping.", message_id)
                continue
            try:
                self._process_one(message_id, always_important, ignored)
                processed_count += 1
            except Exception:  # noqa: BLE001 - one bad message must not kill the poller
                logger.exception("Failed to process message %s", message_id)
                # Phase 1: mark processed to avoid poison-pill retry
                if not self._uses_database and self._store is not None:
                    self._store.mark_processed(message_id)
        return processed_count

    def _is_processed(self, message_id: str) -> bool:
        if self._uses_database:
            from app.database.session import session_scope
            with session_scope() as session:
                return self._email_repo.has_processed(session, message_id)
        return self._store.has_processed(message_id)  # type: ignore[union-attr]

    def _process_one(self, message_id: str, always_important: set[str], ignored: set[str]) -> None:
        raw_message = self._gmail.get_message(message_id)
        email = normalize_gmail_message(raw_message)
        result = triage_service.triage(
            self._ai_provider,
            email,
            always_important_senders=always_important,
            ignored_senders=ignored,
        )

        analysis = result.analysis

        if self._uses_database:
            self._process_one_pg(email, analysis, result)
        else:
            self._process_one_sqlite(email, analysis, result)

        from app.services import metrics
        metrics.increment("emails_processed")

        if result.should_notify_now and analysis is not None:
            self._on_notify(ProcessedEmail(email, analysis, result.notification_tier))
        else:
            metrics.increment("notifications_suppressed")
            logger.info(
                "Message %s tier=%s notified=%s",
                message_id,
                result.notification_tier,
                result.should_notify_now,
            )

    def _process_one_pg(self, email, analysis, result) -> None:
        """Phase 2 Postgres write path (spec §2.1)."""
        from app.config import settings
        from app.database.session import session_scope

        with session_scope() as session:
            msg = self._email_repo.save(
                session,
                user_id=self._user_id,
                email=email,
                analysis=analysis,
                notification_tier=result.notification_tier,
                notified=result.should_notify_now,
                ai_provider_name=settings.ai_provider,
            )

            # Generate embedding for emails scored >=5 (non-tier-"none")
            if analysis is not None and result.notification_tier != "none":
                try:
                    from app.ai.embeddings import get_embedding_provider

                    text = f"{email.subject}\n\n{email.body_text}"
                    vector = get_embedding_provider().embed(text)
                    self._embedding_repo.upsert(
                        session,
                        email_id=msg.id,
                        vector=vector,
                        model=settings.embedding_model,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Embedding generation failed for message %s (non-fatal): %s",
                        email.message_id,
                        exc,
                    )
                    # Embedding failure is enrichment-only — the email row is still committed.

    def _process_one_sqlite(self, email, analysis, result) -> None:
        """Phase 1 SQLite write path (fallback)."""
        from app.database.repositories.processed_messages import NotificationRecord

        record = NotificationRecord(
            message_id=email.message_id,
            thread_id=email.thread_id,
            subject=email.subject,
            sender=email.sender,
            summary=analysis.summary if analysis else "",
            reason=analysis.reason if analysis else "Skipped by deterministic pre-filter.",
            action_items=analysis.action_items if analysis else [],
            importance_score=analysis.importance_score if analysis else 0,
            urgency=analysis.urgency if analysis else "low",
            category=analysis.category if analysis else "other",
            requires_action=analysis.requires_action if analysis else False,
            deadline=analysis.deadline if analysis else None,
            notification_tier=result.notification_tier,
            notified=result.should_notify_now,
            received_at=email.received_at.isoformat(),
        )
        self._store.log_notification(record)  # type: ignore[union-attr]
        self._store.mark_processed(email.message_id)  # type: ignore[union-attr]
