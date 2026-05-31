import unittest
from unittest.mock import MagicMock, patch

from app.services import gemini
from app.services.gemini import GeminiSummaryError, generate_news_summary


def _article(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "headline": f"{ticker} headline",
        "summary": f"{ticker} summary",
    }


class TestGenerateNewsSummary(unittest.TestCase):
    @patch("app.services.gemini.time.sleep", return_value=None)
    @patch("app.services.gemini.genai.GenerativeModel")
    @patch("app.services.gemini.genai.configure")
    def test_splits_news_into_ticker_batches(self, mock_configure, mock_model_cls, mock_sleep):
        model = MagicMock()
        model.generate_content.side_effect = [
            MagicMock(text="• First batch summary"),
            MagicMock(text="• Second batch summary"),
        ]
        mock_model_cls.return_value = model

        news_data = [_article(ticker) for ticker in ["ADTN", "AMPX", "AMZN", "APP", "COHR"]]

        result = generate_news_summary("api-key", news_data)

        self.assertEqual(result, "• First batch summary\n\n• Second batch summary")
        self.assertEqual(model.generate_content.call_count, 2)
        self.assertEqual(
            model.generate_content.call_args_list[0].kwargs["request_options"]["timeout"],
            gemini.GEMINI_TIMEOUT_SECONDS,
        )
        mock_sleep.assert_called_once_with(gemini.GEMINI_BATCH_DELAY_SECONDS)
        mock_configure.assert_called_once_with(api_key="api-key")

    @patch("app.services.gemini.time.sleep", return_value=None)
    @patch("app.services.gemini.genai.GenerativeModel")
    @patch("app.services.gemini.genai.configure")
    def test_raises_after_retry_exhaustion(self, _mock_configure, mock_model_cls, mock_sleep):
        model = MagicMock()
        model.generate_content.side_effect = RuntimeError("deadline exceeded")
        mock_model_cls.return_value = model

        with self.assertRaises(GeminiSummaryError):
            generate_news_summary("api-key", [_article("ADTN")])

        self.assertEqual(model.generate_content.call_count, gemini.GEMINI_MAX_ATTEMPTS)
        self.assertEqual(mock_sleep.call_count, gemini.GEMINI_MAX_ATTEMPTS - 1)


if __name__ == "__main__":
    unittest.main()
