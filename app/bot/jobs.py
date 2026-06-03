import asyncio
import logging

from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.config import FINNHUB_API_KEY, GEMINI_API_KEY, TELEGRAM_CHAT_ID
from app.services.finnhub import fetch_news
from app.services.gemini import GeminiSummaryError, generate_news_summary
from app.services.ibkr import get_portfolio_tickers
from app.services.yahoo import update_earnings_cache

logger = logging.getLogger(__name__)

PORTFOLIO_FETCH_TIMEOUT_SECONDS = 90
EARNINGS_CACHE_REFRESH_TIMEOUT_SECONDS = 180
NEWS_FETCH_TIMEOUT_SECONDS = 120
NEWS_SUMMARY_TIMEOUT_SECONDS = 240
TELEGRAM_SEND_TIMEOUT_SECONDS = 15
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_SAFE_MESSAGE_LENGTH = 3900


def _split_oversized_block(block: str, max_length: int) -> list[str]:
    """Split text that cannot fit by paragraph boundaries."""
    chunks: list[str] = []
    current = ""

    for line in block.splitlines(keepends=True):
        if len(line) > max_length:
            if current:
                chunks.append(current.rstrip())
                current = ""

            for start in range(0, len(line), max_length):
                chunk = line[start : start + max_length].rstrip()
                if chunk:
                    chunks.append(chunk)
            continue

        candidate = current + line
        if len(candidate) > max_length and current:
            chunks.append(current.rstrip())
            current = line
        else:
            current = candidate

    if current.strip():
        chunks.append(current.rstrip())

    return chunks


def _split_message(text: str, max_length: int = TELEGRAM_SAFE_MESSAGE_LENGTH) -> list[str]:
    """Split a Telegram message into chunks below the platform limit."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n\n"):
        separator = "\n\n" if current else ""
        candidate = f"{current}{separator}{paragraph}"
        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            chunks.append(current.rstrip())
            current = ""

        if len(paragraph) <= max_length:
            current = paragraph
        else:
            chunks.extend(_split_oversized_block(paragraph, max_length))

    if current.strip():
        chunks.append(current.rstrip())

    return chunks


async def _get_portfolio_tickers() -> list[str]:
    """Fetch IBKR tickers without blocking the async scheduler."""
    return await asyncio.wait_for(
        asyncio.to_thread(get_portfolio_tickers),
        timeout=PORTFOLIO_FETCH_TIMEOUT_SECONDS,
    )


async def _send_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Send Telegram messages with a bound so error handling cannot hang."""
    message_chunks = _split_message(text)
    logger.info(
        "Sending Telegram message in %s chunk(s), original length=%s.",
        len(message_chunks),
        len(text),
    )

    for chunk_index, chunk in enumerate(message_chunks, start=1):
        logger.info(
            "Sending Telegram message chunk %s/%s, length=%s.",
            chunk_index,
            len(message_chunks),
            len(chunk),
        )
        await asyncio.wait_for(
            context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk),
            timeout=TELEGRAM_SEND_TIMEOUT_SECONDS,
        )


def _summary_unavailable_message(tickers: list[str]) -> str:
    tracked = ", ".join(tickers) if tickers else "unavailable"
    return (
        "⚠️ AI Summary unavailable today due to high server load.\n\n"
        f"Current tracked portfolio: {tracked}"
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

        try:
            summary = await asyncio.wait_for(
                asyncio.to_thread(generate_news_summary, GEMINI_API_KEY, news_data),
                timeout=NEWS_SUMMARY_TIMEOUT_SECONDS,
            )
        except (GeminiSummaryError, TimeoutError):
            logger.exception("Gemini news summary unavailable.")
            await _send_message(context, _summary_unavailable_message(tickers))
            return

        try:
            await _send_message(context, summary)
        except (TelegramError, TimeoutError):
            logger.exception(
                "Morning news summary delivery failed, length=%s.",
                len(summary),
            )
            try:
                await _send_message(
                    context,
                    "• Morning news summary was generated but could not be delivered.",
                )
            except Exception:
                logger.exception("Failed to send morning-news delivery failure notification.")
            return

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
