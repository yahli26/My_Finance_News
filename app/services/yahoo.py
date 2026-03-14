import logging
import asyncio
import random
from datetime import date, datetime
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

_earnings_cache: dict[str, str] = {}


def _normalize_date(value: Any) -> str | None:
    """Normalize Yahoo earnings date values into YYYY-MM-DD."""
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _normalize_date(item)
            if normalized:
                return normalized
        return None

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().strftime("%Y-%m-%d")
        except Exception:
            return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        candidate = raw[:10]
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None


def _extract_earnings_date(calendar: Any) -> str | None:
    """Extract the first earnings date from a Yahoo calendar payload."""
    if calendar is None:
        return None

    if isinstance(calendar, dict):
        for key in ("Earnings Date", "earningsDate", "earnings_date"):
            if key in calendar:
                return _normalize_date(calendar[key])
        return None

    if hasattr(calendar, "loc"):
        try:
            row = calendar.loc["Earnings Date"]
            if hasattr(row, "iloc"):
                return _normalize_date(row.iloc[0])
            return _normalize_date(row)
        except Exception:
            return None

    return None


async def fetch_yahoo_earnings(tickers: list[str]) -> dict[str, str]:
    """Fetch earnings dates from Yahoo Finance for a list of tickers."""
    earnings_by_ticker: dict[str, str] = {}

    def _fetch_single_ticker(sym: str) -> str | None:
        """Isolated synchronous function to run purely within a background thread."""
        calendar = yf.Ticker(sym).calendar
        return _extract_earnings_date(calendar)

    for ticker in tickers:
        symbol = ticker.strip().upper()
        if not symbol:
            continue

        try:
            earnings_date = await asyncio.to_thread(_fetch_single_ticker, symbol)
            if earnings_date:
                earnings_by_ticker[symbol] = earnings_date
            else:
                logger.info("No Yahoo earnings date available for %s", symbol)
        except Exception:
            logger.exception("Failed to fetch Yahoo earnings date for %s", symbol)
        finally:
            # Randomized minimum delay (e.g., 0.8 to 2.2 seconds) to bypass scraping detection
            # while keeping the total scan time short array.
            delay = random.uniform(0.8, 2.2)
            await asyncio.sleep(delay)

    return earnings_by_ticker


async def update_earnings_cache(tickers: list[str]) -> dict[str, str]:
    """Refresh and replace the in-memory earnings cache."""
    global _earnings_cache
    _earnings_cache = await fetch_yahoo_earnings(tickers)
    return dict(_earnings_cache)


def get_earnings_cache() -> dict[str, str]:
    """Return a snapshot of the in-memory earnings cache."""
    return dict(_earnings_cache)
