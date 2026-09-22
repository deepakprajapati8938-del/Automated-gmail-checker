"""
Builds the Telegram Application: registers commands, the free-text fallback,
and the inline-button callback handler. Stores shared state in bot_data so
handlers.py can reach it without global variables.

Phase 2/3: accepts optional session_factory and user_id for Postgres mode.
Phase 1 fallback: accepts store (SQLite).
"""
from __future__ import annotations

import uuid
from typing import Optional

from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.telegram import handlers

BOT_COMMANDS = [
    BotCommand("start", "Connect and get a welcome message"),
    BotCommand("help", "Show what I can do"),
    BotCommand("inbox", "Recently important emails I've seen"),
    BotCommand("important", "Emails scored 7+ this run"),
    BotCommand("today", "Emails received today"),
    BotCommand("deadlines", "Deadlines I've extracted so far"),
    BotCommand("actions", "Emails that need action from you"),
    BotCommand("digest", "Summary of important emails"),
    BotCommand("settings", "Current configuration"),
    BotCommand("metrics", "Internal metrics (Phase 6)"),
    BotCommand("reset", "Clear conversation memory"),
]


def build_application(
    bot_token: str,
    *,
    store=None,
    session_factory=None,
    user_id: Optional[uuid.UUID] = None,
) -> Application:
    app = Application.builder().token(bot_token).build()

    # Phase 1 SQLite fallback
    app.bot_data["store"] = store
    # Phase 2/3 Postgres
    app.bot_data["uses_database"] = session_factory is not None
    app.bot_data["session_factory"] = session_factory
    app.bot_data["user_id"] = user_id

    app.add_handler(CommandHandler("start", handlers.start_cmd))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("inbox", handlers.inbox_cmd))
    app.add_handler(CommandHandler("important", handlers.important_cmd))
    app.add_handler(CommandHandler("today", handlers.today_cmd))
    app.add_handler(CommandHandler("deadlines", handlers.deadlines_cmd))
    app.add_handler(CommandHandler("actions", handlers.actions_cmd))
    app.add_handler(CommandHandler("digest", handlers.digest_cmd))
    app.add_handler(CommandHandler("settings", handlers.settings_cmd))
    app.add_handler(CommandHandler("metrics", handlers.metrics_cmd))
    app.add_handler(CommandHandler("reset", handlers.reset_cmd))
    app.add_handler(CallbackQueryHandler(handlers.callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.free_text_handler))

    async def _post_init(application: Application) -> None:
        await application.bot.set_my_commands(BOT_COMMANDS)

    app.post_init = _post_init

    return app
