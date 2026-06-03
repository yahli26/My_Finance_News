import json
import logging
import time
from collections.abc import Iterable
from collections import defaultdict
from itertools import islice

import google.generativeai as genai

from app.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_SECONDS = 90
GEMINI_MAX_ATTEMPTS = 3
GEMINI_RETRY_BACKOFF_SECONDS = 1
GEMINI_BATCH_SIZE = 4
GEMINI_BATCH_DELAY_SECONDS = 3
GEMINI_MAX_ARTICLES_PER_TICKER = 6


class GeminiSummaryError(RuntimeError):
    """Raised when Gemini cannot produce a usable news summary."""


def _chunked(items: list[str], size: int) -> list[list[str]]:
    """Split items into fixed-size chunks while preserving order."""
    iterator = iter(items)
    chunks: list[list[str]] = []
    while chunk := list(islice(iterator, size)):
        chunks.append(chunk)
    return chunks


def _group_news_by_ticker(news_data: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for article in news_data:
        ticker = str(article.get("ticker") or "UNKNOWN").upper()
        grouped[ticker].append(article)
    return dict(grouped)


def _company_label(article: dict, ticker: str) -> str:
    """Return a readable company label, falling back to the ticker symbol."""
    for key in ("companyName", "company_name", "company", "name"):
        raw_name = article.get(key)
        if raw_name:
            company_name = str(raw_name).strip()
            if company_name and company_name.upper() != ticker:
                return f"{company_name} ({ticker})"

    return ticker


def _iterable_or_empty(value: object) -> list:
    if value is None or isinstance(value, (str, bytes)):
        return []
    if not isinstance(value, Iterable):
        return []

    return list(value)


def _candidate_finish_reasons(response: object) -> list[str]:
    reasons: list[str] = []
    for candidate in _iterable_or_empty(getattr(response, "candidates", None)):
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason is not None:
            reasons.append(str(finish_reason))
    return reasons


def _extract_response_text(response: object) -> str:
    text_parts: list[str] = []

    for candidate in _iterable_or_empty(getattr(response, "candidates", None)):
        content = getattr(candidate, "content", None)
        for part in _iterable_or_empty(getattr(content, "parts", None)):
            text = getattr(part, "text", None)
            if text:
                text_parts.append(str(text))

    summary = "\n".join(text_parts).strip()
    if summary:
        return summary

    finish_reasons = _candidate_finish_reasons(response)
    if finish_reasons:
        logger.warning("Gemini returned no text parts; finish_reasons=%s.", finish_reasons)
        raise GeminiSummaryError(
            f"Gemini returned no text parts; finish_reasons={', '.join(finish_reasons)}."
        )

    try:
        summary = response.text.strip()
    except Exception as e:
        logger.warning("Gemini response did not expose usable text.", exc_info=True)
        raise GeminiSummaryError("Gemini response did not expose usable text.") from e

    if not summary:
        raise GeminiSummaryError("Gemini returned an empty summary.")

    return summary


def _article_timestamp(article: dict) -> int:
    try:
        return int(article.get("datetime") or 0)
    except (TypeError, ValueError):
        return 0


def _limit_articles_for_prompt(news_data: list[dict]) -> list[dict]:
    """Keep the newest items so each ticker prompt stays bounded."""
    return sorted(news_data, key=_article_timestamp, reverse=True)[:GEMINI_MAX_ARTICLES_PER_TICKER]


def _build_prompt(news_data: list[dict]) -> str:
    news_text = json.dumps(_limit_articles_for_prompt(news_data), ensure_ascii=False, indent=2)
    return f"""\
    Below is raw financial news data for stocks in my portfolio:

    {news_text}

    Your task:
    1. Aggressively filter out general market noise, gossip, and insignificant PR announcements.
    2. Isolate only the most critical and financially impactful reports.
    3. Return at most 3 bullet points for this company.
    4. Summarize each critical item in exactly one clear, concise sentence in English, under 220 characters.
    5. Order the bullet points by financial importance, from highest to lowest.
    6. Format the output as a bulleted list using "•" characters, with an empty line between each bullet point for mobile readability on Telegram.

    Return ONLY the formatted English bullet list. No titles, no introductions, no conclusions."""


def _generate_batch_summary(model: genai.GenerativeModel, news_data: list[dict]) -> str:
    prompt = _build_prompt(news_data)

    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = model.generate_content(
                prompt,
                request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
            )
            return _extract_response_text(response)
        except Exception as e:
            if attempt == GEMINI_MAX_ATTEMPTS:
                raise GeminiSummaryError("Gemini failed after all retry attempts.") from e

            logger.warning(
                "Gemini summary generation failed; retrying attempt %d/%d.",
                attempt + 1,
                GEMINI_MAX_ATTEMPTS,
                exc_info=True,
            )
            time.sleep(GEMINI_RETRY_BACKOFF_SECONDS * attempt)


def generate_news_summary(api_key: str, news_data: list[dict]) -> str:
    """Generate a summary of the most critical financial news using Gemini."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    grouped_news = _group_news_by_ticker(news_data)
    ticker_batches = _chunked(list(grouped_news), GEMINI_BATCH_SIZE)
    summaries: list[str] = []

    for batch_index, ticker_batch in enumerate(ticker_batches):
        for ticker in ticker_batch:
            company_news = grouped_news[ticker]
            company_heading = _company_label(company_news[0], ticker)
            company_summary = _generate_batch_summary(model, company_news)
            summaries.append(f"{company_heading}\n{company_summary}")

        if batch_index < len(ticker_batches) - 1:
            time.sleep(GEMINI_BATCH_DELAY_SECONDS)

    if not summaries:
        raise GeminiSummaryError("No news data was available to summarize.")

    return "\n\n".join(summaries)