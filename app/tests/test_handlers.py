import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("FINNHUB_API_KEY", "finnhub-key")
os.environ.setdefault("GEMINI_API_KEY", "gemini-key")

from app.bot.handlers import _test_daily_news_callback


class TestDailyNewsHandler(unittest.IsolatedAsyncioTestCase):
    @patch("app.bot.handlers.TELEGRAM_CHAT_ID", 12345)
    @patch("app.bot.handlers.send_morning_news", new_callable=AsyncMock)
    async def test_test_command_replies_loading_then_runs_morning_news(self, mock_send_morning_news):
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=12345),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        context = SimpleNamespace()

        await _test_daily_news_callback(update, context)

        update.message.reply_text.assert_awaited_once_with("Loading daily news...")
        mock_send_morning_news.assert_awaited_once_with(context)

    @patch("app.bot.handlers.TELEGRAM_CHAT_ID", 12345)
    @patch("app.bot.handlers.send_morning_news", new_callable=AsyncMock)
    async def test_test_command_ignores_unauthorized_chat(self, mock_send_morning_news):
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=67890),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        context = SimpleNamespace()

        await _test_daily_news_callback(update, context)

        update.message.reply_text.assert_not_awaited()
        mock_send_morning_news.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
