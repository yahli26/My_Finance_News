import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("FINNHUB_API_KEY", "finnhub-key")
os.environ.setdefault("GEMINI_API_KEY", "gemini-key")

from app.bot.jobs import send_morning_news
from app.services.gemini import GeminiSummaryError


class TestMorningNewsJob(unittest.IsolatedAsyncioTestCase):
    @patch("app.bot.jobs.TELEGRAM_CHAT_ID", 12345)
    @patch("app.bot.jobs.generate_news_summary", side_effect=GeminiSummaryError("timeout"))
    @patch("app.bot.jobs.fetch_news", return_value=[{"ticker": "ADTN", "headline": "News"}])
    @patch("app.bot.jobs._get_portfolio_tickers", new_callable=AsyncMock)
    async def test_sends_portfolio_fallback_when_gemini_fails(
        self,
        mock_get_tickers,
        _mock_fetch_news,
        _mock_generate_summary,
    ):
        mock_get_tickers.return_value = ["ADTN", "AMPX"]
        context = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        await send_morning_news(context)

        context.bot.send_message.assert_awaited_once()
        _, kwargs = context.bot.send_message.await_args
        self.assertEqual(kwargs["chat_id"], 12345)
        self.assertIn("AI Summary unavailable", kwargs["text"])
        self.assertIn("ADTN, AMPX", kwargs["text"])


if __name__ == "__main__":
    unittest.main()
