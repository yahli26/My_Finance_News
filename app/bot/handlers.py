import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.config import FINNHUB_API_KEY, TELEGRAM_CHAT_ID
from app.services.finnhub import fetch_earnings_calendar
from app.services.ibkr import get_portfolio_tickers

logger = logging.getLogger(__name__)


async def _earnings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with upcoming earnings dates for all portfolio tickers."""
    sender_id = update.effective_chat.id
    if sender_id != TELEGRAM_CHAT_ID:
        logger.warning("Unauthorized access attempt from chat %s", sender_id)
        return

    logger.info("Earnings command received from chat %s", sender_id)

    try:
        tickers = get_portfolio_tickers()
        earnings = fetch_earnings_calendar(FINNHUB_API_KEY, tickers)

        if not earnings:
            await update.message.reply_text("No upcoming earnings found for your portfolio.")
            return

        lines = ["*Upcoming Earnings*"]
        lines.append("_⚠ Dates marked (est.) are API estimates and may be inaccurate._")
        for item in earnings:
            symbol = item.get("symbol", "?")
            raw_date = item.get("date", "?")
            try:
                from datetime import datetime
                formatted_date = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
            except (ValueError, TypeError):
                formatted_date = raw_date

            # Finnhub may include an epsEstimate field; the presence of a
            # non-None value is a weak signal the date is estimated rather
            # than confirmed by the company.
            estimate_tag = " _(est.)_" if item.get("epsEstimate") is not None else ""
            lines.append(f"Ticker: {symbol}, report on: {formatted_date}{estimate_tag}")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception:
        logger.exception("Failed to fetch earnings calendar.")
        await update.message.reply_text("Failed to fetch earnings calendar. Check server logs.")


# Matches any message whose full text (case-insensitive) is "reports" or "earnings"
earnings_handler = MessageHandler(
    filters.TEXT & filters.Regex(r"(?i)^\s*(reports?|earnings?)\s*$"),
    _earnings_callback,
)
