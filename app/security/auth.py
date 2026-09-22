"""
Authorization for the single-owner Telegram bot. Every handler must check
is_authorized() before doing anything else. Always compares the numeric
Telegram user ID — never the @username (spec section 21/22, SECURITY.md #3).
"""
from __future__ import annotations

import logging

from telegram import Update

logger = logging.getLogger(__name__)

UNAUTHORIZED_MESSAGE = "Unauthorized user."


def is_authorized(update: Update, owner_id: int) -> bool:
    user = update.effective_user
    if user is None:
        return False
    authorized = user.id == owner_id
    if not authorized:
        logger.warning("Unauthorized access attempt from telegram user id=%s", user.id)
    return authorized
