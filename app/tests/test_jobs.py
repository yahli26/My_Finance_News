import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")
os.environ.setdefault("FINNHUB_API_KEY", "finnhub-key")
os.environ.setdefault("GEMINI_API_KEY", "gemini-key")

from app.bot.jobs import TELEGRAM_SAFE_MESSAGE_LENGTH, _send_message, send_morning_news
from app.services.gemini import GeminiSummaryError


class TestMorningNewsJob(unittest.IsolatedAsyncioTestCase):
    @patch("app.bot.jobs.TELEGRAM_CHAT_ID", 12345)
    async def test_send_message_splits_oversized_text(self):
        context = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        text = f"{'A' * TELEGRAM_SAFE_MESSAGE_LENGTH}\n\n{'B' * TELEGRAM_SAFE_MESSAGE_LENGTH}"

        await _send_message(context, text)

        self.assertEqual(context.bot.send_message.await_count, 2)
        for call in context.bot.send_message.await_args_list:
            _, kwargs = call
            self.assertEqual(kwargs["chat_id"], 12345)
            self.assertLessEqual(len(kwargs["text"]), TELEGRAM_SAFE_MESSAGE_LENGTH)

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

    @patch("app.bot.jobs.TELEGRAM_CHAT_ID", 12345)
    @patch(
        "app.bot.jobs.generate_news_summary",
        return_value=f"{'A' * TELEGRAM_SAFE_MESSAGE_LENGTH}\n\n{'B' * TELEGRAM_SAFE_MESSAGE_LENGTH}",
    )
    @patch("app.bot.jobs.fetch_news", return_value=[{"ticker": "ADTN", "headline": "News"}])
    @patch("app.bot.jobs._get_portfolio_tickers", new_callable=AsyncMock)
    async def test_sends_oversized_summary_in_chunks(
        self,
        mock_get_tickers,
        _mock_fetch_news,
        _mock_generate_summary,
    ):
        mock_get_tickers.return_value = ["ADTN"]
        context = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        await send_morning_news(context)

        self.assertEqual(context.bot.send_message.await_count, 2)
        sent_texts = [call.kwargs["text"] for call in context.bot.send_message.await_args_list]
        self.assertTrue(all(len(text) <= TELEGRAM_SAFE_MESSAGE_LENGTH for text in sent_texts))
        self.assertNotIn("encountered an error", "\n".join(sent_texts))


if __name__ == "__main__":
    unittest.main()
