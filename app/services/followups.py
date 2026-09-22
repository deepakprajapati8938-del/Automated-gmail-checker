import uuid

from sqlalchemy.orm import Session

from app.database.models import EmailMessage
from app.database.repositories.emails import EmailRepository


def run_followup_sweep(
    session: Session, user_id: uuid.UUID, my_email_address: str, days: int
) -> list[EmailMessage]:
    """
    Fetch stale threads that haven't been followed up on.
    """
    repo = EmailRepository()
    return repo.find_stale_threads(session, user_id, my_email_address, days)
