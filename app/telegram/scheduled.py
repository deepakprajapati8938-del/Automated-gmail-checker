import logging
from datetime import datetime, timezone

from telegram.constants import ParseMode

from app.config import settings
from app.database.repositories.users import UserRepository
from app.database.repositories.events import EventRepository
from app.database.session import session_scope
from app.services.deadlines import run_deadline_sweep
from app.services.followups import run_followup_sweep
from app.telegram.commands import digest_text

logger = logging.getLogger(__name__)


async def deadline_sweep_job(app):
    """Hourly job to check for upcoming deadlines and notify."""
    with session_scope() as session:
        user = UserRepository().get_by_telegram_id(session, settings.telegram_owner_id)
        if not user:
            return

        events = run_deadline_sweep(
            session, user.id, settings.deadline_reminder_window_hours
        )
        if not events:
            return

        event_repo = EventRepository()
        for event in events:
            # Format according to spec section 20
            dt_str = event.event_date
            text = f"⏰ <b>DEADLINE REMINDER</b>\n\n{event.description}\n\n📅 {dt_str}"
            try:
                await app.bot.send_message(
                    chat_id=settings.telegram_owner_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
                event_repo.mark_reminded(session, event.id)
            except Exception as e:
                logger.error("Failed to send deadline reminder: %s", e)


async def followup_sweep_job(app):
    """Daily job to check for stale threads that need follow-up."""
    with session_scope() as session:
        user = UserRepository().get_by_telegram_id(session, settings.telegram_owner_id)
        if not user:
            return

        if not user.email_address:
            logger.warning("User email_address is empty, cannot run followup sweep.")
            return

        stale_messages = run_followup_sweep(
            session, user.id, user.email_address, settings.followup_detection_days
        )
        
        for msg in stale_messages:
            text = (
                f"🔄 <b>FOLLOW-UP SUGGESTION</b>\n\n"
                f"You emailed <b>{msg.sender}</b> {settings.followup_detection_days} days ago but haven't received a reply.\n\n"
                f"Subject: {msg.subject}"
            )
            try:
                await app.bot.send_message(
                    chat_id=settings.telegram_owner_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
                msg.followed_up_at = datetime.now(timezone.utc)
                session.add(msg)
            except Exception as e:
                logger.error("Failed to send followup suggestion: %s", e)


async def daily_digest_job(app):
    """Daily digest job."""
    with session_scope() as session:
        user = UserRepository().get_by_telegram_id(session, settings.telegram_owner_id)
        if not user:
            return
        
        text = digest_text(session, user.id)
    
    try:
        await app.bot.send_message(
            chat_id=settings.telegram_owner_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error("Failed to send daily digest: %s", e)
