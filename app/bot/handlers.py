import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.config import TELEGRAM_CHAT_ID
from app.services.yahoo import get_earnings_cache

logger = logging.getLogger(__name__)


async def _earnings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with upcoming earnings dates for all portfolio tickers."""
    sender_id = update.effective_chat.id
    if sender_id != TELEGRAM_CHAT_ID:
        logger.warning("Unauthorized access attempt from chat %s", sender_id)
        return

    logger.info("Earnings command received from chat %s", sender_id)

    try:
        earnings = get_earnings_cache()

        if not earnings:
            await update.message.reply_text(
                "Earnings cache is warming up. Please try again in a minute."
            )
            return

        lines = ["*Upcoming Earnings*"]
        for symbol, raw_date in sorted(earnings.items(), key=lambda item: item[1]):
            try:
                formatted_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
            except (ValueError, TypeError):
                formatted_date = raw_date

            lines.append(f"Ticker {symbol} - Earnings date: {formatted_date}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception:
        logger.exception("Failed to read earnings cache.")
        await update.message.reply_text("Failed to read earnings cache. Check server logs.")


# Matches any message whose full text (case-insensitive) is "reports" or "earnings"
earnings_handler = MessageHandler(
    filters.TEXT & filters.Regex(r"(?i)^\s*(reports?|earnings?)\s*$"),
    _earnings_callback,
)
