import logging
import os
import json
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# US Eastern timezone (UTC-5 / UTC-4 DST). Earnings dates are aligned to
# the US market calendar, so anchoring "today" to US/Eastern avoids the
# problem of a UTC server clock rolling past midnight and skipping a report
# that is still "today" on Wall Street.
_US_EASTERN_OFFSET = timezone(timedelta(hours=-5))
_SEEN_NEWS_CACHE_PATH = os.path.join(os.path.dirname(__file__), "_seen_news_cache.json")


def _today_eastern() -> str:
    """Return today's date string (YYYY-MM-DD) in US Eastern time."""
    return datetime.now(_US_EASTERN_OFFSET).strftime("%Y-%m-%d")


def _yesterday_eastern() -> str:
    """Return yesterday's date string (YYYY-MM-DD) in US Eastern time."""
    return (datetime.now(_US_EASTERN_OFFSET) - timedelta(days=1)).strftime("%Y-%m-%d")


def _is_within_last_24_hours(article: dict, cutoff_utc: datetime) -> bool:
    """Return True only for articles published strictly within the last 24 hours."""
    published_at = article.get("datetime")
    if published_at is None:
        return False

    try:
        published_ts = int(published_at)
    except (TypeError, ValueError):
        return False

    published_dt = datetime.fromtimestamp(published_ts, tz=timezone.utc)
    return published_dt > cutoff_utc


def _article_key(article: dict) -> str:
    """Build a stable key so we can deduplicate news across daily runs."""
    if article.get("id") is not None:
        return f"id:{article['id']}"
    if article.get("url"):
        return f"url:{article['url']}"

    headline = str(article.get("headline", "")).strip().lower()
    source = str(article.get("source", "")).strip().lower()
    published_at = str(article.get("datetime", "")).strip()
    return f"fallback:{headline}|{source}|{published_at}"


def _load_seen_news() -> dict[str, int]:
    """Load seen-article keys mapped to unix timestamps from disk."""
    if not os.path.exists(_SEEN_NEWS_CACHE_PATH):
        return {}

    try:
        with open(_SEEN_NEWS_CACHE_PATH, "r", encoding="utf-8") as cache_file:
            data = json.load(cache_file)
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        logger.warning("Failed to load seen-news cache; continuing without it.", exc_info=True)

    return {}


def _save_seen_news(seen_news: dict[str, int]) -> None:
    """Persist seen-article keys so the next daily run can skip duplicates."""
    try:
        with open(_SEEN_NEWS_CACHE_PATH, "w", encoding="utf-8") as cache_file:
            json.dump(seen_news, cache_file)
    except Exception:
        logger.warning("Failed to save seen-news cache.", exc_info=True)


def fetch_news(api_key: str, tickers: list[str]) -> list[dict]:
    """Retrieve company news, then keep only unique items from the last 24 hours."""
    from_date = _yesterday_eastern()
    today = _today_eastern()
    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=24)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    seen_news = _load_seen_news()

    # Keep only recent cache entries so disk state stays bounded.
    seen_news = {
        key: ts
        for key, ts in seen_news.items()
        if ts >= int((cutoff_utc - timedelta(hours=24)).timestamp())
    }

    aggregated_news: list[dict] = []

    for ticker in tickers:
        try:
            response = requests.get(
                f"{FINNHUB_BASE_URL}/company-news",
                params={
                    "symbol": ticker,
                    "from": from_date,
                    "to": today,
                    "token": api_key,
                },
                timeout=30,
            )
            response.raise_for_status()
            articles = response.json()
        except requests.RequestException:
            logger.warning(
                "Failed to fetch Finnhub news for ticker '%s'; skipping and continuing.",
                ticker,
                exc_info=True,
            )
            continue

        for article in articles:
            article["ticker"] = ticker

        aggregated_news.extend(articles)

    filtered_news: list[dict] = []
    for article in aggregated_news:
        if not _is_within_last_24_hours(article, cutoff_utc):
            continue

        key = _article_key(article)
        if key in seen_news:
            continue

        seen_news[key] = now_ts
        filtered_news.append(article)

    _save_seen_news(seen_news)
    return filtered_news