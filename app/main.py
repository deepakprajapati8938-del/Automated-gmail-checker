"""
Entrypoint. Runs two things in one process, one asyncio loop:
  1. The Telegram bot (long polling) — handles commands/callbacks/free text.
  2. A background Gmail poll loop — ingests new mail, triages it, and hands
     off any "notify now" results back into the same event loop to send via
     Telegram.

Phase 2/3: when DATABASE_URL is set, initialises Postgres, resolves the User
row, and wires all handlers to Postgres repositories. Falls back to Phase 1
SQLite path when DATABASE_URL is unset.

No inbound HTTP port is opened (see DEPLOYMENT.md).
"""
from __future__ import annotations

import asyncio
import logging
import signal

from app.ai.base import get_provider
from app.config import settings
from app.email.gmail import GmailAuthError, GmailClient
from app.email.processor import EmailProcessor, ProcessedEmail
from app.telegram.bot import build_application
from app.telegram.notifications import send_notification
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


async def _gmail_poll_loop(app, processor: EmailProcessor, pending: list[ProcessedEmail]) -> None:
    while True:
        try:
            count = await asyncio.to_thread(processor.run_poll_cycle)
            if count:
                logger.info("Poll cycle processed %d new email(s).", count)
        except GmailAuthError:
            logger.error(
                "Gmail auth invalid/expired. Run scripts/gmail_oauth_setup.py and restart."
            )
        except Exception as exc:  # noqa: BLE001
            # Check for DB errors (like OperationalError) to avoid crashing the poll loop
            if "OperationalError" in str(type(exc)):
                logger.error("Database connection lost during poll loop. Will retry next cycle: %s", exc)
                # Phase 6: Ensure metrics increment here if we had a metrics module (will add later)
            else:
                logger.exception("Unexpected error during Gmail poll cycle.")

        while pending:
            processed_email = pending.pop(0)
            await send_notification(app, settings.telegram_owner_id, processed_email)

        await asyncio.sleep(settings.gmail_poll_interval_seconds)


async def run() -> None:
    ai_provider = get_provider()

    try:
        gmail = GmailClient(settings.gmail_token_path, settings.gmail_state_path)
    except GmailAuthError as exc:
        logger.error("%s", exc)
        logger.error("Run: python scripts/gmail_oauth_setup.py")
        return

    # --- Phase 2: Postgres setup ---
    session_factory = None
    user_id = None
    store = None

    if settings.uses_database():
        from app.database.session import init_engine, session_scope

        from tenacity import retry, wait_exponential, stop_after_attempt
        
        @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
        def _init_db_with_retry(url):
            init_engine(url)
            
        logger.info("DATABASE_URL is set — using Postgres (Phase 2) path.")
        _init_db_with_retry(settings.database_url)

        # Resolve the user row once at startup
        from app.database.repositories.users import UserRepository

        email_address = ""
        try:
            profile = gmail.service.users().getProfile(userId="me").execute()
            email_address = profile.get("emailAddress", "")
        except Exception:  # noqa: BLE001
            logger.warning("Could not fetch Gmail profile email address — user row will have blank email.")

        with session_scope() as session:
            user = UserRepository().get_or_create(
                session,
                telegram_user_id=settings.telegram_owner_id,
                email_address=email_address,
            )
            user_id = user.id
            logger.info("Resolved user_id=%s for telegram_user_id=%s", user_id, settings.telegram_owner_id)

        from app.database.session import session_scope as sf
        session_factory = sf

        from app.database.repositories.emails import EmailRepository
        from app.database.repositories.embeddings import EmbeddingRepository

        processor = EmailProcessor(
            gmail=gmail,
            ai_provider=ai_provider,
            on_notify=(pending_notifications := []).append,
            user_id=user_id,
            email_repo=EmailRepository(),
            embedding_repo=EmbeddingRepository(),
            session_factory=session_factory,
        )
        telegram_app = build_application(
            settings.telegram_bot_token,
            session_factory=session_factory,
            user_id=user_id,
        )
    else:
        # --- Phase 1: SQLite fallback ---
        logger.info("DATABASE_URL not set — using Phase 1 SQLite path.")
        from app.database.repositories.processed_messages import Store

        store = Store(settings.sqlite_path)
        pending_notifications: list[ProcessedEmail] = []
        processor = EmailProcessor(
            gmail=gmail,
            ai_provider=ai_provider,
            on_notify=pending_notifications.append,
            store=store,
        )
        telegram_app = build_application(settings.telegram_bot_token, store=store)

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info(
        "Telegram bot started (long polling). Gmail poll interval=%ss",
        settings.gmail_poll_interval_seconds,
    )

    if settings.uses_database():
        from app.telegram import scheduled
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(scheduled.deadline_sweep_job, "interval", hours=1, args=[telegram_app])
        scheduler.add_job(scheduled.followup_sweep_job, "cron", hour=9, args=[telegram_app])
        scheduler.add_job(scheduled.daily_digest_job, "cron", hour=settings.digest_hour_utc, args=[telegram_app])
        scheduler.start()
        logger.info("Phase 4 proactive scheduler started.")

    poll_task = asyncio.create_task(
        _gmail_poll_loop(telegram_app, processor, pending_notifications)
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows fallback: Ctrl+C still raises KeyboardInterrupt

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutting down...")
        poll_task.cancel()
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
