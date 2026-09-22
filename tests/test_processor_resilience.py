import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.telegram.notifications import send_notification
from app.email.processor import ProcessedEmail

@pytest.mark.asyncio
async def test_telegram_unavailable_does_not_crash():
    app = MagicMock()
    app.bot.send_message = AsyncMock(side_effect=Exception("Telegram is down"))
    
    mock_email = MagicMock()
    mock_email.message_id = "msg-123"
    mock_email.thread_id = "thread-123"
    mock_email.subject = "Test"
    
    mock_analysis = MagicMock()
    mock_analysis.summary = "Test summary"
    mock_analysis.reason = "Test reason"
    mock_analysis.action_items = []
    mock_analysis.deadline = None

    processed = ProcessedEmail(email=mock_email, analysis=mock_analysis, notification_tier="notify")

    # This should log and increment metrics, but NOT raise an exception.
    await send_notification(app, 12345, processed)
