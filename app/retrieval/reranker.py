"""
Phase 2: Reciprocal Rank Fusion (RRF) — merges multiple ranked result lists
into one deduped, re-ranked list. Used by hybrid_search() to combine vector
search results and keyword search results (spec section 15).
"""
from __future__ import annotations

import uuid

from app.database.models import EmailMessage

RRF_K = 60  # standard constant; higher = smoother blend, less sensitive to top ranks


def rerank(ranked_lists: list[list[EmailMessage]]) -> list[EmailMessage]:
    """Merge N ranked lists via Reciprocal Rank Fusion. Returns deduped list ordered by score desc."""
    scores: dict[uuid.UUID, float] = {}
    by_id: dict[uuid.UUID, EmailMessage] = {}

    for ranked in ranked_lists:
        for rank, msg in enumerate(ranked, start=1):
            scores[msg.id] = scores.get(msg.id, 0.0) + 1.0 / (RRF_K + rank)
            by_id[msg.id] = msg

    sorted_ids = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [by_id[eid] for eid in sorted_ids]
