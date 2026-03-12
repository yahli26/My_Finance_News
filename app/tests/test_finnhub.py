import unittest
from unittest.mock import patch, MagicMock

from requests.exceptions import HTTPError

from app.services.finnhub import fetch_news, fetch_earnings_calendar

# --- Sample fixtures ---

PLTR_NEWS = [
    {"headline": "Palantir wins contract", "summary": "Big deal announced"},
    {"headline": "Palantir Q1 preview", "summary": "Analysts optimistic"},
]

FLNC_NEWS = [
    {"headline": "Fluence earnings beat", "summary": "Revenue up 30%"},
]

EARNINGS_CALENDAR_RAW = {
    "earningsCalendar": [
        {"symbol": "PLTR", "date": "2026-04-10", "epsEstimate": 0.12},
        {"symbol": "NOPE", "date": "2026-04-15", "epsEstimate": 0.50},
        {"symbol": "FLNC", "date": "2025-01-01", "epsEstimate": 0.05},
        {"symbol": "FLNC", "date": "2026-06-20", "epsEstimate": 0.08},
    ]
}

PORTFOLIO_TICKERS = ["PLTR", "FLNC"]
DUMMY_API_KEY = "test_key"


class TestFetchNews(unittest.TestCase):
    """Tests for the fetch_news function."""

    @patch("app.services.finnhub.requests.get")
    def test_aggregates_news_for_multiple_tickers(self, mock_get):
        """News from all tickers is aggregated into one list with ticker injected."""
        pltr_response = MagicMock()
        pltr_response.json.return_value = [dict(a) for a in PLTR_NEWS]
        pltr_response.raise_for_status = MagicMock()

        flnc_response = MagicMock()
        flnc_response.json.return_value = [dict(a) for a in FLNC_NEWS]
        flnc_response.raise_for_status = MagicMock()

        mock_get.side_effect = [pltr_response, flnc_response]

        result = fetch_news(DUMMY_API_KEY, PORTFOLIO_TICKERS)

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(result), 3)

        # Verify ticker injection
        self.assertEqual(result[0]["ticker"], "PLTR")
        self.assertEqual(result[1]["ticker"], "PLTR")
        self.assertEqual(result[2]["ticker"], "FLNC")

        # Verify data integrity
        self.assertEqual(result[0]["headline"], "Palantir wins contract")
        self.assertEqual(result[2]["headline"], "Fluence earnings beat")

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


class TestFetchEarningsCalendar(unittest.TestCase):
    """Tests for the fetch_earnings_calendar function."""

    @patch("app.services.finnhub.datetime")
    @patch("app.services.finnhub.requests.get")
    def test_filters_and_sorts_earnings(self, mock_get, mock_datetime):
        """Only owned tickers with future dates are returned, sorted ascending."""
        mock_datetime.now.return_value.strftime.return_value = "2026-03-11"

        mock_response = MagicMock()
        mock_response.json.return_value = EARNINGS_CALENDAR_RAW
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_earnings_calendar(DUMMY_API_KEY, PORTFOLIO_TICKERS)

        # NOPE is not owned -> filtered out
        # FLNC 2025-01-01 is in the past -> filtered out
        # PLTR 2026-04-10 and FLNC 2026-06-20 remain
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["symbol"], "PLTR")
        self.assertEqual(result[0]["date"], "2026-04-10")
        self.assertEqual(result[1]["symbol"], "FLNC")
        self.assertEqual(result[1]["date"], "2026-06-20")

    @patch("app.services.finnhub.requests.get")
    def test_earnings_http_error_propagates(self, mock_get):
        """An HTTP error from the earnings endpoint is raised properly."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError(
            response=MagicMock(status_code=401)
        )
        mock_get.return_value = mock_response

        with self.assertRaises(HTTPError):
            fetch_earnings_calendar(DUMMY_API_KEY, PORTFOLIO_TICKERS)


if __name__ == "__main__":
    unittest.main()