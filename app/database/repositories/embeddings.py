"""
Phase 2: EmbeddingRepository — store and query pgvector embeddings.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import EmailEmbedding, EmailMessage


class EmbeddingRepository:
    def upsert(
        self,
        session: Session,
        *,
        email_id: uuid.UUID,
        vector: list[float],
        model: str,
    ) -> EmailEmbedding:
        """Insert or replace the embedding for this email."""
        existing = session.query(EmailEmbedding).filter_by(email_message_id=email_id).first()
        if existing is not None:
            existing.embedding = vector
            existing.model = model
            return existing
        emb = EmailEmbedding(
            id=uuid.uuid4(),
            email_message_id=email_id,
            embedding=vector,
            model=model,
        )
        session.add(emb)
        session.flush()
        return emb

    def similarity_search(
        self,
        session: Session,
        *,
        user_id: uuid.UUID,
        query_vector: list[float],
        limit: int = 10,
        restrict_to_ids: Optional[set[uuid.UUID]] = None,
    ) -> list[tuple[EmailMessage, float]]:
        """Return (EmailMessage, distance) pairs ordered by cosine distance ascending."""
        # pgvector cosine distance operator: <=>
        distance_expr = EmailEmbedding.embedding.cosine_distance(query_vector).label("distance")

        q = (
            session.query(EmailMessage, distance_expr)
            .join(EmailEmbedding, EmailMessage.id == EmailEmbedding.email_message_id)
            .filter(EmailMessage.user_id == user_id)
        )
        if restrict_to_ids:
            q = q.filter(EmailMessage.id.in_(restrict_to_ids))

        rows = q.order_by(distance_expr.asc()).limit(limit).all()
        return [(msg, float(dist)) for msg, dist in rows]
