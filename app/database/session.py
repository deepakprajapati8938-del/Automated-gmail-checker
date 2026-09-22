"""
SQLAlchemy engine and session management (Phase 2).

Call init_engine(database_url) once at startup (in app/main.py when
settings.uses_database() is True), then use session_scope() per request/task.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_SessionLocal: sessionmaker | None = None


def init_engine(database_url: str) -> None:
    """Create the SQLAlchemy engine and configure the session factory.
    Must be called once at application startup before any session_scope() call.
    """
    global _SessionLocal
    engine = create_engine(
        database_url,
        pool_pre_ping=True,   # detect stale connections
        pool_size=5,
        max_overflow=10,
    )
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional session scope. Commits on success, rolls back on error."""
    if _SessionLocal is None:
        raise RuntimeError(
            "Database engine not initialised. Call init_engine(database_url) first."
        )
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
