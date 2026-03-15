import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

from requests.exceptions import HTTPError

from app.services.finnhub import fetch_news

# --- Sample fixtures ---

NOW_TS = int(datetime.now(timezone.utc).timestamp())

PLTR_NEWS = [
    {
        "id": 1001,
        "headline": "Palantir wins contract",
        "summary": "Big deal announced",
        "datetime": NOW_TS - 3600,
    },
    {
        "id": 1002,
        "headline": "Palantir old article",
        "summary": "Stale item",
        "datetime": NOW_TS - (26 * 3600),
    },
]

FLNC_NEWS = [
    {
        "id": 2001,
        "headline": "Fluence earnings beat",
        "summary": "Revenue up 30%",
        "datetime": NOW_TS - 1200,
    },
]

PORTFOLIO_TICKERS = ["PLTR", "FLNC"]
DUMMY_API_KEY = "test_key"


class TestFetchNews(unittest.TestCase):
    """Tests for the fetch_news function."""

    @patch("app.services.finnhub._save_seen_news")
    @patch("app.services.finnhub._load_seen_news", return_value={})
    @patch("app.services.finnhub.requests.get")
    def test_aggregates_news_for_multiple_tickers(self, mock_get, _mock_load_seen, _mock_save_seen):
        """News from all tickers is aggregated, filtered to 24h, with ticker injected."""
        pltr_response = MagicMock()
        pltr_response.json.return_value = [dict(a) for a in PLTR_NEWS]
        pltr_response.raise_for_status = MagicMock()

        flnc_response = MagicMock()
        flnc_response.json.return_value = [dict(a) for a in FLNC_NEWS]
        flnc_response.raise_for_status = MagicMock()

        mock_get.side_effect = [pltr_response, flnc_response]

        result = fetch_news(DUMMY_API_KEY, PORTFOLIO_TICKERS)

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(result), 2)

        # Verify ticker injection
        self.assertEqual(result[0]["ticker"], "PLTR")
        self.assertEqual(result[1]["ticker"], "FLNC")

        # Verify data integrity
        self.assertEqual(result[0]["headline"], "Palantir wins contract")
        self.assertEqual(result[1]["headline"], "Fluence earnings beat")

    @patch("app.services.finnhub._save_seen_news")
    @patch("app.services.finnhub._load_seen_news", return_value={})
    @patch("app.services.finnhub._yesterday_eastern", return_value="2026-03-14")
    @patch("app.services.finnhub._today_eastern", return_value="2026-03-15")
    @patch("app.services.finnhub.requests.get")
    def test_uses_yesterday_to_today_window(
        self,
        mock_get,
        _mock_today,
        _mock_yesterday,
        _mock_load_seen,
        _mock_save_seen,
    ):
        """API params use a 48-hour fetch window from yesterday to today."""
        mock_response = MagicMock()
        mock_response.json.return_value = [dict(a) for a in FLNC_NEWS]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetch_news(DUMMY_API_KEY, ["FLNC"])

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["from"], "2026-03-14")
        self.assertEqual(kwargs["params"]["to"], "2026-03-15")

    @patch("app.services.finnhub._save_seen_news")
    @patch("app.services.finnhub._load_seen_news")
    @patch("app.services.finnhub.requests.get")
    def test_skips_articles_seen_in_previous_run(self, mock_get, mock_load_seen, _mock_save_seen):
        """Articles already seen in prior runs are excluded to avoid day-to-day repeats."""
        seen = {"id:1001": int(datetime.now(timezone.utc).timestamp())}
        mock_load_seen.return_value = seen

        mock_response = MagicMock()
        mock_response.json.return_value = [dict(a) for a in PLTR_NEWS]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_news(DUMMY_API_KEY, ["PLTR"])

        self.assertEqual(len(result), 0)

    @patch("app.services.finnhub.requests.get")
    def test_news_http_error_propagates(self, mock_get):
        """An HTTP error from the API is raised, not silently swallowed."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError(
            response=MagicMock(status_code=429)
        )
        mock_get.return_value = mock_response

        with self.assertRaises(HTTPError):
            fetch_news(DUMMY_API_KEY, ["PLTR"])

if __name__ == "__main__":
    unittest.main()