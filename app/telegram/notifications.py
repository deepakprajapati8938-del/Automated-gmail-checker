"""
Formats and sends the proactive "IMPORTANT EMAIL" Telegram notifications
described in spec section 3A / 18. The LLM never calls this directly — only
app.email.processor invokes it, after app.services.triage has already made
the notification-tier decision (ARCHITECTURE.md #7).
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application

logger = logging.getLogger(__name__)

TIER_EMOJI = {"immediate": "🔴", "notify": "🟠", "digest": "🟡", "none": "⚪"}


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_notification(processed_email) -> str:
    email = processed_email.email
    analysis = processed_email.analysis
    emoji = TIER_EMOJI.get(processed_email.notification_tier, "⚪")

    action_text = "\n".join(f"• {a}" for a in analysis.action_items) if analysis.action_items else "No action needed."

    lines = [
        f"{emoji} IMPORTANT EMAIL",
        "",
        f"📩 <b>{_escape_html(email.subject)}</b>",
        "",
        _escape_html(analysis.summary),
        "",
        "<b>Why this matters:</b>",
        _escape_html(analysis.reason),
        "",
        "<b>Action:</b>",
        _escape_html(action_text),
    ]
    if analysis.deadline:
        lines.insert(6, f"📅 Deadline: {_escape_html(analysis.deadline)}")
    return "\n".join(lines)


def build_keyboard(message_id: str, thread_id: str) -> InlineKeyboardMarkup:
    gmail_url = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Why Important", callback_data=f"why:{message_id}"),
                InlineKeyboardButton("Open Email", url=gmail_url),
            ],
            [
                InlineKeyboardButton("👍 Important", callback_data=f"fb:important:{message_id}"),
                InlineKeyboardButton("👎 Not Important", callback_data=f"fb:not_important:{message_id}"),
            ],
            [
                InlineKeyboardButton("🔕 Ignore Sender", callback_data=f"fb:ignore_sender:{message_id}"),
                InlineKeyboardButton("⭐ Always Important", callback_data=f"fb:always_important:{message_id}"),
            ],
        ]
    )


async def send_notification(app: Application, owner_id: int, processed_email) -> None:
    text = format_notification(processed_email)
    keyboard = build_keyboard(processed_email.email.message_id, processed_email.email.thread_id)
    from app.services import metrics
    try:
        await app.bot.send_message(
            chat_id=owner_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        metrics.increment("notifications_sent")
    except Exception:  # noqa: BLE001 - notification delivery must never crash the poller
        metrics.increment("telegram_errors")
        logger.exception("Failed to send Telegram notification for message %s", processed_email.email.message_id)
