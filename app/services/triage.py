"""
Business logic for deciding (a) whether an email is even worth an AI call, and
(b) given the AI's recommended importance score, what the backend's
notification policy actually does. The LLM only *recommends* a score — this
module is what enforces the spec's notification-tier table in code, so a
prompt injection or a flaky model can never directly cause an unwanted
Telegram send. See spec sections 12 and 25, and ARCHITECTURE.md #7.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.base import AIProvider, AIProviderError
from app.ai.schemas import EmailAnalysis
from app.agents.prompts.triage import TRIAGE_SYSTEM_PROMPT, build_triage_user_prompt
from app.email.parser import NormalizedEmail, extract_email_address

logger = logging.getLogger(__name__)

BULK_MAIL_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}

NotificationTier = str  # "none" | "digest" | "notify" | "immediate"


@dataclass
class TriageResult:
    analysis: EmailAnalysis | None  # None if AI was skipped entirely
    notification_tier: NotificationTier
    should_notify_now: bool


def should_skip_ai(email: NormalizedEmail, *, always_important_senders: set[str], ignored_senders: set[str]) -> bool:
    """Deterministic pre-filter, spec #25. Biased toward calling the AI (a
    false 'skip' is worse than an extra AI call for a personal-scale inbox)."""
    sender_email = extract_email_address(email.sender)

    if sender_email in always_important_senders:
        return False  # never skip a sender the user explicitly starred

    if sender_email in ignored_senders:
        return True

    if BULK_MAIL_LABELS.intersection(email.labels):
        return True

    if not email.body_text.strip() and not email.subject.strip("() ").lower().startswith("no subject"):
        # Essentially empty email with no useful signal.
        if len(email.subject.strip()) < 3:
            return True

    return False




def score_to_tier(importance_score: int) -> NotificationTier:
    """Spec section 12's notification policy table, enforced in code."""
    if importance_score <= 4:
        return "none"
    if importance_score <= 6:
        return "digest"
    if importance_score <= 8:
        return "notify"
    return "immediate"


def analyze_email(provider: AIProvider, email: NormalizedEmail) -> EmailAnalysis:
    """Calls the AI provider and returns a validated EmailAnalysis. Raises
    AIProviderError on failure — caller decides the fallback behavior."""
    user_prompt = build_triage_user_prompt(
        subject=email.subject,
        sender=email.sender,
        received_at_iso=email.received_at.isoformat(),
        body_text=email.body_text,
    )
    return provider.complete_structured(TRIAGE_SYSTEM_PROMPT, user_prompt, EmailAnalysis)


def fallback_analysis(email: NormalizedEmail) -> EmailAnalysis:
    """Used when the AI provider is unavailable. Never silently drops the
    email — flags it as 'needs review' at a tier that gets it in front of the
    user via the digest rather than an immediate ping, per TELEGRAM_AGENT.md #7."""
    return EmailAnalysis(
        importance_score=6,
        urgency="medium",
        category="other",
        requires_action=False,
        summary=f"AI analysis unavailable. Subject: {email.subject}",
        reason="AI provider was unavailable at ingestion time; flagged for manual review.",
        deadline=None,
        action_items=["Review this email manually — automated analysis failed."],
        entities=[],
        confidence=0.0,
    )


def triage(
    provider: AIProvider,
    email: NormalizedEmail,
    *,
    always_important_senders: set[str],
    ignored_senders: set[str],
) -> TriageResult:
    from app.services import metrics
    if should_skip_ai(email, always_important_senders=always_important_senders, ignored_senders=ignored_senders):
        metrics.increment("emails_skipped")
        logger.info("Skipping AI triage for message %s (deterministic pre-filter)", email.message_id)
        return TriageResult(analysis=None, notification_tier="none", should_notify_now=False)

    try:
        analysis = analyze_email(provider, email)
        metrics.increment("emails_classified")
    except AIProviderError as exc:
        metrics.increment("AI_failures")
        logger.error("AI triage failed for message %s: %s", email.message_id, exc)
        analysis = fallback_analysis(email)

    tier = score_to_tier(analysis.importance_score)
    if extract_email_address(email.sender) in always_important_senders:
        tier = "immediate"

    should_notify_now = tier in ("notify", "immediate")
    return TriageResult(analysis=analysis, notification_tier=tier, should_notify_now=should_notify_now)
