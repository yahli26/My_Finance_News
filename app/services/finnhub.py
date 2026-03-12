import logging
from datetime import datetime, timedelta

import requests

from app.config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def fetch_news(api_key: str, tickers: list[str]) -> list[dict]:
    """Retrieve the last 24 hours of company news for all given tickers."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

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
    """Fetch upcoming earnings dates for portfolio tickers, sorted chronologically."""
    today = datetime.now().strftime("%Y-%m-%d")

    response = requests.get(
        f"{FINNHUB_BASE_URL}/calendar/earnings",
        params={"token": api_key},
        timeout=30,
    )
    response.raise_for_status()

    earnings_data = response.json().get("earningsCalendar", [])

    filtered = [
        item
        for item in earnings_data
        if item.get("symbol") in tickers and item.get("date", "") >= today
    ]

    filtered.sort(key=lambda item: item["date"])

    return filtered