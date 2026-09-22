"""
Phase 2: UserRepository — get or create the single User row for this agent instance.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.database.models import User


class UserRepository:
    def get_or_create(
        self,
        session: Session,
        *,
        telegram_user_id: int,
        email_address: str,
    ) -> User:
        """Return existing User or insert a new one. Idempotent."""
        user = session.query(User).filter_by(telegram_user_id=telegram_user_id).first()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                telegram_user_id=telegram_user_id,
                email_address=email_address,
            )
            session.add(user)
            session.flush()  # populate id without full commit
        return user
