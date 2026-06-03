import unittest
from types import SimpleNamespace
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
    def test_formats_news_as_company_sections(self, mock_configure, mock_model_cls, mock_sleep):
        model = MagicMock()
        model.generate_content.side_effect = [
            MagicMock(text="• ADTN summary"),
            MagicMock(text="• AMPX summary"),
            MagicMock(text="• AMZN summary"),
            MagicMock(text="• APP summary"),
            MagicMock(text="• COHR summary"),
        ]
        mock_model_cls.return_value = model

        news_data = [_article(ticker) for ticker in ["ADTN", "AMPX", "AMZN", "APP", "COHR"]]

        result = generate_news_summary("api-key", news_data)

        self.assertEqual(
            result,
            (
                "ADTN\n"
                "• ADTN summary\n\n"
                "AMPX\n"
                "• AMPX summary\n\n"
                "AMZN\n"
                "• AMZN summary\n\n"
                "APP\n"
                "• APP summary\n\n"
                "COHR\n"
                "• COHR summary"
            ),
        )
        self.assertEqual(model.generate_content.call_count, 5)
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

    @patch("app.services.gemini.time.sleep", return_value=None)
    @patch("app.services.gemini.genai.GenerativeModel")
    @patch("app.services.gemini.genai.configure")
    def test_company_section_heading_uses_company_name_when_available(
        self,
        _mock_configure,
        mock_model_cls,
        _mock_sleep,
    ):
        model = MagicMock()
        model.generate_content.side_effect = [
            MagicMock(text="• ADTN summary"),
            MagicMock(text="• AMPX summary"),
        ]
        mock_model_cls.return_value = model

        news_data = [
            {
                **_article("ADTN"),
                "companyName": "ADTRAN Holdings Inc",
            },
            _article("AMPX"),
        ]

        result = generate_news_summary("api-key", news_data)

        self.assertEqual(
            result,
            (
                "ADTRAN Holdings Inc (ADTN)\n"
                "• ADTN summary\n\n"
                "AMPX\n"
                "• AMPX summary"
            ),
        )

    @patch("app.services.gemini.time.sleep", return_value=None)
    @patch("app.services.gemini.genai.GenerativeModel")
    @patch("app.services.gemini.genai.configure")
    def test_raises_when_candidates_have_no_text_parts(
        self,
        _mock_configure,
        mock_model_cls,
        mock_sleep,
    ):
        model = MagicMock()
        model.generate_content.return_value = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason=1,
                    content=SimpleNamespace(parts=[]),
                )
            ],
        )
        mock_model_cls.return_value = model

        with self.assertRaises(GeminiSummaryError):
            generate_news_summary("api-key", [_article("ADTN")])

        self.assertEqual(model.generate_content.call_count, gemini.GEMINI_MAX_ATTEMPTS)
        self.assertEqual(mock_sleep.call_count, gemini.GEMINI_MAX_ATTEMPTS - 1)

    @patch("app.services.gemini.time.sleep", return_value=None)
    @patch("app.services.gemini.genai.GenerativeModel")
    @patch("app.services.gemini.genai.configure")
    def test_limits_articles_per_ticker_in_prompt(
        self,
        _mock_configure,
        mock_model_cls,
        _mock_sleep,
    ):
        model = MagicMock()
        model.generate_content.return_value = MagicMock(text="• ADTN summary")
        mock_model_cls.return_value = model

        news_data = [
            {
                **_article("ADTN"),
                "headline": f"ADTN headline {index}",
                "datetime": index,
            }
            for index in range(gemini.GEMINI_MAX_ARTICLES_PER_TICKER + 2)
        ]

        generate_news_summary("api-key", news_data)

        prompt = model.generate_content.call_args.args[0]
        self.assertIn('"datetime": 7', prompt)
        self.assertIn('"datetime": 2', prompt)
        self.assertNotIn('"datetime": 1', prompt)
        self.assertNotIn('"datetime": 0', prompt)


if __name__ == "__main__":
    unittest.main()
