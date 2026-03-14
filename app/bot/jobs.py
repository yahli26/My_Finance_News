import logging

from telegram.ext import ContextTypes

from app.config import FINNHUB_API_KEY, GEMINI_API_KEY, TELEGRAM_CHAT_ID
from app.services.finnhub import fetch_news
from app.services.gemini import generate_news_summary
from app.services.ibkr import get_portfolio_tickers
from app.services.yahoo import update_earnings_cache

logger = logging.getLogger(__name__)


async def refresh_earnings_cache_job(context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    """Scheduled job: refresh in-memory Yahoo earnings cache from IBKR holdings."""
    logger.info("Earnings cache refresh job triggered.")

    try:
        tickers = get_portfolio_tickers()
        if not tickers:
            logger.warning("No tickers returned from IBKR; skipping cache refresh.")
            return

        updated = await update_earnings_cache(tickers)
        logger.info("Earnings cache refreshed for %s tickers.", len(updated))

    except Exception:
        logger.exception("Earnings cache refresh job failed.")


async def refresh_earnings_cache(context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    """Backward-compatible alias for existing scheduler imports."""
    await refresh_earnings_cache_job(context)


async def send_morning_news(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job: fetch portfolio news and send a Gemini-summarized digest."""
    logger.info("Morning news job triggered.")

    try:
        tickers = get_portfolio_tickers()
        if not tickers:
            logger.warning("No tickers returned from IBKR; aborting morning news.")
            return

        news_data = fetch_news(FINNHUB_API_KEY, tickers)
        if not news_data:
            await context.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text="• No portfolio news found for today.",
            )
            return

        summary = generate_news_summary(GEMINI_API_KEY, news_data)
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
        logger.info("Morning news sent successfully.")

    except Exception:
        logger.exception("Morning news job failed.")
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="• Morning news job encountered an error. Check server logs.",
        )
