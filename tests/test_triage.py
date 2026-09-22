from datetime import datetime, timezone

import pytest

from app.email.parser import NormalizedEmail
from app.services.triage import score_to_tier, should_skip_ai


def make_email(**overrides) -> NormalizedEmail:
    defaults = dict(
        message_id="m1",
        thread_id="t1",
        sender="Alice <alice@example.com>",
        recipients=["me@example.com"],
        cc=[],
        subject="Test subject",
        body_text="Some body text.",
        snippet="Some body",
        received_at=datetime.now(timezone.utc),
        labels=[],
        has_attachments=False,
        attachment_metadata=[],
    )
    defaults.update(overrides)
    return NormalizedEmail(**defaults)


@pytest.mark.parametrize(
    "score,expected_tier",
    [
        (0, "none"),
        (4, "none"),
        (5, "digest"),
        (6, "digest"),
        (7, "notify"),
        (8, "notify"),
        (9, "immediate"),
        (10, "immediate"),
    ],
)
def test_score_to_tier_matches_spec_table(score, expected_tier):
    assert score_to_tier(score) == expected_tier


def test_should_skip_ai_for_promotions_label():
    email = make_email(labels=["CATEGORY_PROMOTIONS"])
    assert should_skip_ai(email, always_important_senders=set(), ignored_senders=set()) is True


def test_should_not_skip_always_important_sender_even_if_promotions():
    email = make_email(labels=["CATEGORY_PROMOTIONS"])
    assert (
        should_skip_ai(
            email,
            always_important_senders={"alice@example.com"},
            ignored_senders=set(),
        )
        is False
    )


def test_should_skip_ai_for_ignored_sender():
    email = make_email()
    assert (
        should_skip_ai(email, always_important_senders=set(), ignored_senders={"alice@example.com"})
        is True
    )


def test_should_not_skip_normal_email():
    email = make_email()
    assert should_skip_ai(email, always_important_senders=set(), ignored_senders=set()) is False
