import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram import Update, Message
from app.telegram.handlers import free_text_handler
from app.config import settings

@pytest.fixture
def mock_update():
    update = AsyncMock(spec=Update)
    update.message = AsyncMock(spec=Message)
    update.effective_user = MagicMock(id=settings.telegram_owner_id)
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot_data = {"uses_database": True, "session_factory": MagicMock(), "user_id": 123}
    return context

@pytest.mark.asyncio
async def test_free_text_handler_empty_string(mock_update, mock_context):
    mock_update.message.text = ""
    # With empty text, it should not crash.
    with patch("app.telegram.handlers.is_authorized", return_value=True):
        await free_text_handler(mock_update, mock_context)
    mock_update.message.reply_text.assert_called()

@pytest.mark.asyncio
async def test_free_text_handler_large_string(mock_update, mock_context):
    mock_update.message.text = "A" * 10000
    with patch("app.telegram.handlers.is_authorized", return_value=True):
        await free_text_handler(mock_update, mock_context)
    mock_update.message.reply_text.assert_called()

@pytest.mark.asyncio
async def test_free_text_handler_emoji(mock_update, mock_context):
    mock_update.message.text = "👍" * 100
    with patch("app.telegram.handlers.is_authorized", return_value=True):
        await free_text_handler(mock_update, mock_context)
    mock_update.message.reply_text.assert_called()
