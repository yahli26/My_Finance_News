import logging
from contextlib import asynccontextmanager
from datetime import time, timezone

import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

from app.config import TELEGRAM_TOKEN
from app.bot.handlers import earnings_handler
from app.bot.jobs import send_morning_news

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Telegram Application
# ---------------------------------------------------------------------------
# The ApplicationBuilder automatically creates a JobQueue when APScheduler is
# installed (python-telegram-bot[job-queue]). Do NOT call run_polling() —
# updates arrive via the FastAPI webhook instead.
bot_app: Application = Application.builder().token(TELEGRAM_TOKEN).build()


# ---------------------------------------------------------------------------
# FastAPI lifespan: start / stop the bot around the server process
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register message handlers
    bot_app.add_handler(earnings_handler)

    # Schedule the daily morning-news digest at 06:00 IST (= 04:00 UTC)
    bot_app.job_queue.run_daily(
        send_morning_news,
        time=time(4, 0, 0, tzinfo=timezone.utc),
    )

    await bot_app.initialize()
    await bot_app.start()
    logger.info("Telegram bot started.")

    yield  # server is live

    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("Telegram bot shut down.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check():
    """Uptime-monitor ping endpoint — keeps the cloud dyno awake."""
    return {"status": "alive"}


@app.post("/webhook")
async def webhook(request: Request):
    """
    Receive Telegram updates pushed over HTTPS.

    Telegram sends a JSON payload; we deserialise it into an Update object
    and hand it to the bot application for dispatch.
    """
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
