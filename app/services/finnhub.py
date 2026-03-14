import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# US Eastern timezone (UTC-5 / UTC-4 DST). Earnings dates are aligned to
# the US market calendar, so anchoring "today" to US/Eastern avoids the
# problem of a UTC server clock rolling past midnight and skipping a report
# that is still "today" on Wall Street.
_US_EASTERN_OFFSET = timezone(timedelta(hours=-5))


def _today_eastern() -> str:
    """Return today's date string (YYYY-MM-DD) in US Eastern time."""
    return datetime.now(_US_EASTERN_OFFSET).strftime("%Y-%m-%d")


def fetch_news(api_key: str, tickers: list[str]) -> list[dict]:
    """Retrieve the last 24 hours of company news for all given tickers."""
    today = _today_eastern()
    yesterday = (datetime.now(_US_EASTERN_OFFSET) - timedelta(days=1)).strftime("%Y-%m-%d")

    aggregated_news: list[dict] = []

    for ticker in tickers:
        response = requests.get(
            f"{FINNHUB_BASE_URL}/company-news",
            params={
                "symbol": ticker,
                "from": yesterday,
                "to": today,
                "token": api_key,
            },
            timeout=30,
        )
        response.raise_for_status()

        articles = response.json()
        for article in articles:
            article["ticker"] = ticker

        aggregated_news.extend(articles)

    return aggregated_news