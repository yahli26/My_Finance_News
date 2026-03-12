import logging
from datetime import datetime, timedelta, timezone

import requests

from app.config import FINNHUB_API_KEY

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


def fetch_earnings_calendar(api_key: str, tickers: list[str]) -> list[dict]:
    """Fetch upcoming earnings dates for portfolio tickers, sorted chronologically.

    Only the *earliest* upcoming report per ticker is kept.  This prevents a
    wide search window from pulling in a later quarter's estimated date and
    silently overwriting the imminent one.

    Note: Finnhub free-tier dates labelled as "estimated" are algorithmic
    projections based on historical patterns and may be inaccurate.  Only
    dates explicitly confirmed by the company's Investor Relations page or
    SEC filings should be considered reliable.
    """
    today = _today_eastern()
    future = (datetime.now(_US_EASTERN_OFFSET) + timedelta(days=100)).strftime("%Y-%m-%d")

    response = requests.get(
        f"{FINNHUB_BASE_URL}/calendar/earnings",
        params={"from": today, "to": future, "token": api_key},
        timeout=30,
    )
    response.raise_for_status()

    earnings_data = response.json().get("earningsCalendar", [])

    # Filter to portfolio tickers whose date is today-or-later, then
    # sort so the earliest date per ticker comes first.
    filtered = [
        item
        for item in earnings_data
        if item.get("symbol") in tickers and item.get("date", "") >= today
    ]
    filtered.sort(key=lambda item: item["date"])

    # Keep only the first (earliest) occurrence for each ticker.
    seen: set[str] = set()
    deduplicated: list[dict] = []
    for item in filtered:
        symbol = item.get("symbol")
        if symbol not in seen:
            seen.add(symbol)
            deduplicated.append(item)

    return deduplicated