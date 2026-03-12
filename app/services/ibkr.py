import time
import logging
import xml.etree.ElementTree as ET

import requests

from app.config import IBKR_TOKEN, IBKR_QUERY_ID

logger = logging.getLogger(__name__)

IBKR_BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
CURRENCY_SYMBOLS = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "ILS", "BASE_SUMMARY"}

REFERENCE_WAIT_SECONDS = 3


def _request_reference_code() -> str:
    """Step 1: Request a reference code from the IBKR Flex Web Service."""
    url = f"{IBKR_BASE_URL}/SendRequest"
    params = {"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": 3}

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)

    status = root.findtext("Status")
    if status != "Success":
        error_msg = root.findtext("ErrorMessage", "Unknown error")
        raise RuntimeError(f"IBKR reference request failed: {error_msg}")

    reference_code = root.findtext("ReferenceCode")
    if not reference_code:
        raise RuntimeError("IBKR response missing ReferenceCode")

    logger.info("Received IBKR ReferenceCode: %s", reference_code)
    return reference_code


def _download_report(reference_code: str) -> str:
    """Step 2: Download the XML report using the reference code."""
    url = f"{IBKR_BASE_URL}/GetStatement"
    params = {"t": IBKR_TOKEN, "q": reference_code, "v": 3}

    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()

    return response.text


def parse_symbols(xml_text: str) -> list[str]:
    """Parse the IBKR XML report and extract unique ticker symbols, ignoring currencies."""
    root = ET.fromstring(xml_text)
    symbols = set()

    for elem in root.iter():
        symbol = elem.get("symbol")
        if symbol and symbol.upper() not in CURRENCY_SYMBOLS:
            symbols.add(symbol.upper())

    return sorted(symbols)


def get_portfolio_tickers() -> list[str]:
    """Full two-step flow: get reference code, wait, download report, parse symbols."""
    logger.info("Starting IBKR portfolio fetch...")

    reference_code = _request_reference_code()

    logger.info("Waiting %d seconds before downloading report...", REFERENCE_WAIT_SECONDS)
    time.sleep(REFERENCE_WAIT_SECONDS)

    xml_report = _download_report(reference_code)
    tickers = parse_symbols(xml_report)

    logger.info("Fetched %d tickers: %s", len(tickers), tickers)
    return tickers
