import json
import logging

import google.generativeai as genai

from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


def generate_news_summary(api_key: str, news_data: list[dict]) -> str:
    """Generate a summary of the most critical financial news using Gemini."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    news_text = json.dumps(news_data, ensure_ascii=False, indent=2)

    prompt = f"""\
    Below is raw financial news data for stocks in my portfolio:

    {news_text}

    Your task:
    1. Aggressively filter out general market noise, gossip, and insignificant PR announcements.
    2. Isolate only the most critical and financially impactful reports.
    3. Summarize each critical item in exactly one clear, concise sentence in English.
    4. Order the bullet points by financial importance, from highest to lowest.
    5. Format the output as a bulleted list using "•" characters, with an empty line between each bullet point for mobile readability on Telegram.

    Return ONLY the formatted English bullet list. No titles, no introductions, no conclusions."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"• An error occurred while processing this morning's news. Error: {e}"