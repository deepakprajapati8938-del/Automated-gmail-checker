"""
Wires Telegram updates to command implementations. Every handler enforces
authorization first (spec section 21, SECURITY.md #3) before touching any
email data.

Phase 2/3: handlers dispatch to Postgres-backed commands when
settings.uses_database() is True, else fall back to Phase 1 SQLite Store.
"""
from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.config import settings
from app.security.auth import UNAUTHORIZED_MESSAGE, is_authorized
from app.security.rate_limit import RateLimiter
from app.telegram import commands

logger = logging.getLogger(__name__)

_agent_rate_limiter = RateLimiter(max_per_minute=10)

def _reply_kwargs() -> dict:
    return {"parse_mode": ParseMode.HTML, "disable_web_page_preview": True}


async def _reply(update: Update, text: str) -> None:
    await update.message.reply_text(text, **_reply_kwargs())


def _uses_db(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.bot_data.get("uses_database"))


def _get_pg_context(context: ContextTypes.DEFAULT_TYPE):
    """Return (session_factory, user_id) for Postgres-backed handlers."""
    return context.bot_data["session_factory"], context.bot_data["user_id"]


def _store(context: ContextTypes.DEFAULT_TYPE):
    return context.bot_data["store"]


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _reply(
        update,
        "👋 Connected. I'll notify you here when something important shows up in your inbox.\n\n"
        "Send /help to see what I can do.",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _reply(update, commands.HELP_TEXT)


async def inbox_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.inbox_text_pg(session, user_id)
    else:
        text = commands.inbox_text(_store(context))
    await _reply(update, text)


async def important_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.important_text_pg(session, user_id)
    else:
        text = commands.important_text(_store(context))
    await _reply(update, text)


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.today_text_pg(session, user_id)
    else:
        text = commands.today_text(_store(context))
    await _reply(update, text)


async def deadlines_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.deadlines_text_pg(session, user_id)
    else:
        text = commands.deadlines_text(_store(context))
    await _reply(update, text)


async def actions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.actions_text_pg(session, user_id)
    else:
        text = commands.actions_text(_store(context))
    await _reply(update, text)


async def digest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.digest_text_pg(session, user_id)
    else:
        text = commands.digest_text(_store(context))
    await _reply(update, text)


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _uses_db(context):
        sf, user_id = _get_pg_context(context)
        with sf() as session:
            text = commands.settings_text_pg(session, user_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Delete all my data", callback_data="delete_my_data_confirm")]
        ])
        await update.message.reply_text(text, reply_markup=keyboard, **_reply_kwargs())
    else:
        text = commands.SETTINGS_TEXT
        await _reply(update, text)

async def metrics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _reply(update, commands.metrics_text())

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation memory (/reset command, Phase 3)."""
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if not _uses_db(context):
        await _reply(update, "Conversation memory requires Postgres (Phase 2). No memory to clear.")
        return
    from app.services.conversation_memory import ConversationMemory
    sf, user_id = _get_pg_context(context)
    with sf() as session:
        ConversationMemory().clear(session, user_id)
    await _reply(update, "🧹 Conversation memory cleared.")


# ---------------------------------------------------------------------------
# Free-text handler (Phase 3: conversational agent)
# ---------------------------------------------------------------------------

async def free_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update, settings.telegram_owner_id):
        await update.message.reply_text(UNAUTHORIZED_MESSAGE)
        return

    if not _agent_rate_limiter.allow():
        await _reply(update, "You're sending messages faster than I can process them. Give me a moment.")
        return

    if not _uses_db(context):
        await _reply(
            update,
            "Free-text conversation requires the Postgres backend (Phase 2). "
            "Try /inbox, /important, /today, /deadlines, /actions, or /digest instead.",
        )
        return

    user_message = update.message.text
    sf, user_id = _get_pg_context(context)

    try:
        from app.agents.email_agent import EmailAgent
        from app.ai.base import get_provider
        from app.database.repositories.emails import EmailRepository
        from app.services.conversation_memory import ConversationMemory

        with sf() as session:
            memory = ConversationMemory()
            context_text = memory.get_context(session, user_id)

            ai_provider = get_provider()
            gmail_client = context.bot_data.get("gmail_client")
            agent = EmailAgent(
                ai_provider=ai_provider,
                session=session,
                user_id=user_id,
                gmail_client=gmail_client,
            )
            answer = agent.answer(user_message, context_text)

            # Append source citations (formatted in Python — agent never formats these)
            reply_text = answer.text
            if answer.source_message_ids:
                email_repo = EmailRepository()
                source_lines = []
                for mid in answer.source_message_ids:
                    e = email_repo.get_by_message_id(session, mid)
                    if e is not None:
                        date_str = e.received_at.date() if e.received_at else "?"
                        source_lines.append(f'Source: "{e.subject}" — received {date_str}')
                if source_lines:
                    reply_text = f"{reply_text}\n\n" + "\n".join(source_lines)

            memory.record_turn(session, user_id, ai_provider, user_message, answer.text)

    except Exception as exc:  # noqa: BLE001
        logger.error("Free-text agent failed: %s", exc)
        reply_text = "AI is temporarily unavailable, try again in a bit."

    await update.message.reply_text(reply_text, **_reply_kwargs())


# ---------------------------------------------------------------------------
# Callback handler (inline buttons)
# ---------------------------------------------------------------------------

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_authorized(update, settings.telegram_owner_id):
        await query.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
        return

    await query.answer()
    data = query.data or ""

    if data.startswith("why:"):
        message_id = data.split(":", 1)[1]
        if _uses_db(context):
            sf, user_id = _get_pg_context(context)
            with sf() as session:
                text = commands.why_important_text_pg(session, user_id, message_id)
        else:
            text = commands.why_important_text(_store(context), message_id)
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    if data.startswith("fb:"):
        _, feedback_type, message_id = data.split(":", 2)
        if _uses_db(context):
            sf, user_id = _get_pg_context(context)
            from app.database.repositories.emails import EmailRepository
            from app.database.repositories.feedback import FeedbackRepository
            with sf() as session:
                email = EmailRepository().get_by_message_id(session, message_id)
                if email is not None:
                    FeedbackRepository().record(session, email_id=email.id, feedback_type=feedback_type)
        else:
            _store(context).record_feedback(message_id, feedback_type)

        ack = {
            "important": "👍 Thanks — noted as important.",
            "not_important": "👎 Thanks — noted as not important.",
            "ignore_sender": "🔕 Got it — I'll ignore this sender going forward.",
            "always_important": "⭐ Got it — always flagging this sender as important.",
        }.get(feedback_type, "Noted.")
        await query.message.reply_text(ack)
        logger.info("Feedback recorded: %s for message %s", feedback_type, message_id)
        return

    if data == "delete_my_data_confirm":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Yes, delete everything", callback_data="delete_my_data_execute"),
                InlineKeyboardButton("Cancel", callback_data="delete_my_data_cancel")
            ]
        ])
        await query.message.reply_text("⚠️ Are you sure you want to delete all your email records, feedback, and settings? This is irreversible.", reply_markup=keyboard)
        return

    if data == "delete_my_data_cancel":
        await query.message.reply_text("Cancelled data deletion.")
        return

    if data == "delete_my_data_execute":
        if _uses_db(context):
            sf, user_id = _get_pg_context(context)
            with sf() as session:
                from sqlalchemy import text
                session.execute(text("DELETE FROM email_messages WHERE user_id = :id"), {"id": user_id})
            await query.message.reply_text("✅ All your data has been deleted.")
        else:
            await query.message.reply_text("Data deletion only supported for Postgres (Phase 2).")
        return

    logger.warning("Unrecognized callback data: %s", data)
