import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.yahoo as yahoo


class TestYahooEarningsCache(unittest.TestCase):
    def setUp(self):
        yahoo._earnings_cache = {}

    @patch("app.services.yahoo.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.services.yahoo.yf.Ticker")
    def test_fetch_yahoo_earnings_extracts_first_date(self, mock_ticker, mock_sleep):
        ticker_obj = MagicMock()
        ticker_obj.calendar = {"Earnings Date": ["2026-07-30", "2026-10-30"]}
        mock_ticker.return_value = ticker_obj

        result = asyncio.run(yahoo.fetch_yahoo_earnings(["pltr"]))

        self.assertEqual(result, {"PLTR": "2026-07-30"})
        self.assertEqual(mock_sleep.await_count, 1)

    @patch("app.services.yahoo.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.services.yahoo.yf.Ticker")
    def test_fetch_yahoo_earnings_skips_missing_or_failed_symbols(self, mock_ticker, mock_sleep):
        ok = MagicMock()
        ok.calendar = {"Earnings Date": "2026-08-15"}

        missing = MagicMock()
        missing.calendar = {}

        mock_ticker.side_effect = [ok, missing, RuntimeError("boom")]

        result = asyncio.run(yahoo.fetch_yahoo_earnings(["PLTR", "FLNC", "MSFT"]))

        self.assertEqual(result, {"PLTR": "2026-08-15"})
        self.assertEqual(mock_sleep.await_count, 3)

    @patch("app.services.yahoo.fetch_yahoo_earnings", new_callable=AsyncMock)
    def test_update_overwrites_and_get_returns_snapshot(self, mock_fetch):
        mock_fetch.return_value = {"PLTR": "2026-07-30"}

        asyncio.run(yahoo.update_earnings_cache(["PLTR"]))
        snapshot = yahoo.get_earnings_cache()
        snapshot["PLTR"] = "1999-01-01"

        self.assertEqual(yahoo.get_earnings_cache(), {"PLTR": "2026-07-30"})


if __name__ == "__main__":
    unittest.main()
