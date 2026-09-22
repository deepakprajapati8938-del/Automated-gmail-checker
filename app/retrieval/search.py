"""
Phase 2: Hybrid search — metadata pre-filter → vector search + keyword search → RRF merge.
Falls back to keyword-only if the embedding call fails (spec section 15).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import EmailMessage
from app.database.repositories.emails import EmailRepository
from app.database.repositories.embeddings import EmbeddingRepository
from app.retrieval.reranker import rerank

logger = logging.getLogger(__name__)

_email_repo = EmailRepository()
_embedding_repo = EmbeddingRepository()


def hybrid_search(
    session: Session,
    *,
    user_id: uuid.UUID,
    query_text: Optional[str] = None,
    sender: Optional[str] = None,
    category: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 10,
) -> list[EmailMessage]:
    """
    Full hybrid search (spec section 15):
      1. Metadata pre-filter (sender/category/date) → candidate pool.
      2. Vector search (cosine similarity) over that pool.
      3. Keyword search (ILIKE) over that pool.
      4. RRF merge and return top `limit` results.

    Falls back to keyword-only if embedding generation fails.
    Returns results ordered by combined relevance score.
    """
    # Step 1: metadata pre-filter
    if any([sender, category, start, end]):
        candidates = _email_repo.filtered(
            session, user_id, sender=sender, category=category, start=start, end=end
        )
        candidate_ids: Optional[set[uuid.UUID]] = {c.id for c in candidates}
    else:
        candidate_ids = None

    ranked_lists: list[list[EmailMessage]] = []

    if query_text:
        # Step 2: vector search
        vector_results: list[EmailMessage] = []
        try:
            from app.ai.embeddings import get_embedding_provider

            query_vector = get_embedding_provider().embed(query_text)
            pairs = _embedding_repo.similarity_search(
                session,
                user_id=user_id,
                query_vector=query_vector,
                limit=limit * 3,
                restrict_to_ids=candidate_ids,
            )
            vector_results = [msg for msg, _dist in pairs]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding call failed during hybrid search, using keyword-only: %s", exc)

        ranked_lists.append(vector_results)

        # Step 3: keyword search
        keyword_results = _email_repo.keyword_search(session, user_id, query_text, limit=limit * 3)
        if candidate_ids:
            keyword_results = [m for m in keyword_results if m.id in candidate_ids]
        ranked_lists.append(keyword_results)

    elif candidate_ids is not None:
        # No query_text — return metadata-filtered candidates directly
        return candidates[:limit]

    else:
        # No filters at all — return recent notified
        return _email_repo.recent_notified(session, user_id, limit=limit)

    # Step 4: RRF merge
    merged = rerank(ranked_lists)
    return merged[:limit]
