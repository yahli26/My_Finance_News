import asyncio
import logging

from telegram.ext import ContextTypes

from app.config import FINNHUB_API_KEY, GEMINI_API_KEY, TELEGRAM_CHAT_ID
from app.services.finnhub import fetch_news
from app.services.gemini import generate_news_summary
from app.services.ibkr import get_portfolio_tickers
from app.services.yahoo import update_earnings_cache

logger = logging.getLogger(__name__)

PORTFOLIO_FETCH_TIMEOUT_SECONDS = 90
EARNINGS_CACHE_REFRESH_TIMEOUT_SECONDS = 180
NEWS_FETCH_TIMEOUT_SECONDS = 120
NEWS_SUMMARY_TIMEOUT_SECONDS = 45
TELEGRAM_SEND_TIMEOUT_SECONDS = 15


async def _get_portfolio_tickers() -> list[str]:
    """Fetch IBKR tickers without blocking the async scheduler."""
    return await asyncio.wait_for(
        asyncio.to_thread(get_portfolio_tickers),
        timeout=PORTFOLIO_FETCH_TIMEOUT_SECONDS,
    )


async def _send_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Send Telegram messages with a bound so error handling cannot hang."""
    await asyncio.wait_for(
        context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text),
        timeout=TELEGRAM_SEND_TIMEOUT_SECONDS,
    )


async def refresh_earnings_cache_job(context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    """Scheduled job: refresh in-memory Yahoo earnings cache from IBKR holdings."""
    logger.info("Earnings cache refresh job triggered.")

    try:
        tickers = await _get_portfolio_tickers()
        if not tickers:
            logger.warning("No tickers returned from IBKR; skipping cache refresh.")
            return

        updated = await asyncio.wait_for(
            update_earnings_cache(tickers),
            timeout=EARNINGS_CACHE_REFRESH_TIMEOUT_SECONDS,
        )
        logger.info("Earnings cache refreshed for %s tickers.", len(updated))

    except TimeoutError:
        logger.exception("Earnings cache refresh job timed out.")
    except Exception:
        logger.exception("Earnings cache refresh job failed.")


async def refresh_earnings_cache(context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    """Backward-compatible alias for existing scheduler imports."""
    await refresh_earnings_cache_job(context)


async def send_morning_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job: fetch portfolio news and send a Gemini-summarized digest."""
    logger.info("Morning news job triggered.")

    try:
        tickers = await _get_portfolio_tickers()
        if not tickers:
            logger.warning("No tickers returned from IBKR; aborting morning news.")
            return

        news_data = await asyncio.wait_for(
            asyncio.to_thread(fetch_news, FINNHUB_API_KEY, tickers),
            timeout=NEWS_FETCH_TIMEOUT_SECONDS,
        )
        if not news_data:
            await _send_message(context, "• No portfolio news found for today.")
            return

        summary = await asyncio.wait_for(
            asyncio.to_thread(generate_news_summary, GEMINI_API_KEY, news_data),
            timeout=NEWS_SUMMARY_TIMEOUT_SECONDS,
        )
        await _send_message(context, summary)
        logger.info("Morning news sent successfully.")

    except TimeoutError:
        logger.exception("Morning news job timed out.")
        try:
            await _send_message(
                context,
                "• Morning news job timed out while contacting an external service.",
            )
        except Exception:
            logger.exception("Failed to send morning-news timeout notification.")
    except Exception:
        logger.exception("Morning news job failed.")
        try:
            await _send_message(
                context,
                "• Morning news job encountered an error. Check server logs.",
            )
        except Exception:
            logger.exception("Failed to send morning-news failure notification.")
