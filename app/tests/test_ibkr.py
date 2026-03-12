import unittest
from unittest.mock import patch, MagicMock

from app.services.ibkr import parse_symbols, get_portfolio_tickers

# --- Sample XML fixtures ---

SAMPLE_REFERENCE_RESPONSE_OK = """<?xml version="1.0" encoding="utf-8"?>
<FlexStatementResponse timestamp="20260311">
    <Status>Success</Status>
    <ReferenceCode>REF123456</ReferenceCode>
</FlexStatementResponse>"""

SAMPLE_REFERENCE_RESPONSE_FAIL = """<?xml version="1.0" encoding="utf-8"?>
<FlexStatementResponse timestamp="20260311">
    <Status>Fail</Status>
    <ErrorMessage>Invalid token</ErrorMessage>
</FlexStatementResponse>"""

SAMPLE_REFERENCE_RESPONSE_NO_CODE = """<?xml version="1.0" encoding="utf-8"?>
<FlexStatementResponse timestamp="20260311">
    <Status>Success</Status>
</FlexStatementResponse>"""

SAMPLE_REPORT_XML = """<?xml version="1.0" encoding="utf-8"?>
<FlexQueryResponse queryName="MyQuery" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567">
      <OpenPositions>
        <OpenPosition symbol="PLTR" quantity="100" />
        <OpenPosition symbol="MSFT" quantity="50" />
        <OpenPosition symbol="FLNC" quantity="200" />
        <OpenPosition symbol="USD" quantity="5000" />
        <OpenPosition symbol="EUR" quantity="1200" />
      </OpenPositions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""

SAMPLE_REPORT_XML_EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<FlexQueryResponse queryName="MyQuery" type="AF">
  <FlexStatements count="0">
  </FlexStatements>
</FlexQueryResponse>"""

SAMPLE_REPORT_XML_ONLY_CURRENCIES = """<?xml version="1.0" encoding="utf-8"?>
<FlexQueryResponse queryName="MyQuery" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567">
      <OpenPositions>
        <OpenPosition symbol="USD" quantity="5000" />
        <OpenPosition symbol="EUR" quantity="1200" />
        <OpenPosition symbol="BASE_SUMMARY" quantity="0" />
      </OpenPositions>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""

MALFORMED_XML = """<not valid xml><<<<"""


# =========================================================================
# 1. Unit Tests — XML Parsing
# =========================================================================
class TestParseSymbols(unittest.TestCase):
    """Test the XML parser in isolation."""

    def test_extracts_tickers_and_ignores_currencies(self):
        result = parse_symbols(SAMPLE_REPORT_XML)
        self.assertEqual(result, ["FLNC", "MSFT", "PLTR"])
        self.assertNotIn("USD", result)
        self.assertNotIn("EUR", result)

    def test_empty_report_returns_empty_list(self):
        result = parse_symbols(SAMPLE_REPORT_XML_EMPTY)
        self.assertEqual(result, [])

    def test_only_currencies_returns_empty_list(self):
        result = parse_symbols(SAMPLE_REPORT_XML_ONLY_CURRENCIES)
        self.assertEqual(result, [])

    def test_duplicate_symbols_are_deduplicated(self):
        xml_with_dupes = """<?xml version="1.0" encoding="utf-8"?>
        <Root>
            <Pos symbol="AAPL" /><Pos symbol="aapl" /><Pos symbol="MSFT" />
        </Root>"""
        result = parse_symbols(xml_with_dupes)
        self.assertEqual(result, ["AAPL", "MSFT"])

    def test_malformed_xml_raises(self):
        with self.assertRaises(Exception):
            parse_symbols(MALFORMED_XML)


# =========================================================================
# 2. Integration Flow — Happy Path (mocked HTTP + sleep)
# =========================================================================
class TestGetPortfolioTickersHappyPath(unittest.TestCase):
    """Mock the two-step HTTP dance to verify the happy path."""

    @patch("app.services.ibkr.time.sleep", return_value=None)
    @patch("app.services.ibkr.requests.get")
    def test_successful_two_step_flow(self, mock_get, mock_sleep):
        # First call → returns reference code XML
        ref_response = MagicMock()
        ref_response.status_code = 200
        ref_response.text = SAMPLE_REFERENCE_RESPONSE_OK
        ref_response.raise_for_status = MagicMock()

        # Second call → returns the actual report XML
        report_response = MagicMock()
        report_response.status_code = 200
        report_response.text = SAMPLE_REPORT_XML
        report_response.raise_for_status = MagicMock()

        mock_get.side_effect = [ref_response, report_response]

        tickers = get_portfolio_tickers()

        # Verify result
        self.assertEqual(tickers, ["FLNC", "MSFT", "PLTR"])

        # Verify two HTTP calls were made
        self.assertEqual(mock_get.call_count, 2)

        # Verify sleep was called (the wait between steps)
        mock_sleep.assert_called_once()

    @patch("app.services.ibkr.time.sleep", return_value=None)
    @patch("app.services.ibkr.requests.get")
    def test_reference_code_passed_to_second_request(self, mock_get, mock_sleep):
        ref_response = MagicMock()
        ref_response.text = SAMPLE_REFERENCE_RESPONSE_OK
        ref_response.raise_for_status = MagicMock()

        report_response = MagicMock()
        report_response.text = SAMPLE_REPORT_XML
        report_response.raise_for_status = MagicMock()

        mock_get.side_effect = [ref_response, report_response]

        get_portfolio_tickers()

        # The second call's params should include the reference code
        second_call_params = mock_get.call_args_list[1][1].get(
            "params", mock_get.call_args_list[1][0][1] if len(mock_get.call_args_list[1][0]) > 1 else {}
        )
        self.assertIn("REF123456", str(second_call_params))


# =========================================================================
# 3. Edge Cases and Error Handling
# =========================================================================
class TestGetPortfolioTickersErrors(unittest.TestCase):
    """Force error conditions and verify graceful handling."""

    @patch("app.services.ibkr.requests.get")
    def test_http_error_on_reference_request(self, mock_get):
        """Simulate a 500 server error on step 1."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("500 Server Error")
        mock_get.return_value = mock_response

        with self.assertRaises(Exception) as ctx:
            get_portfolio_tickers()
        self.assertIn("500", str(ctx.exception))

    @patch("app.services.ibkr.time.sleep", return_value=None)
    @patch("app.services.ibkr.requests.get")
    def test_http_error_on_report_download(self, mock_get, mock_sleep):
        """Simulate step 1 success but step 2 returns 404."""
        ref_response = MagicMock()
        ref_response.text = SAMPLE_REFERENCE_RESPONSE_OK
        ref_response.raise_for_status = MagicMock()

        error_response = MagicMock()
        error_response.raise_for_status.side_effect = Exception("404 Not Found")

        mock_get.side_effect = [ref_response, error_response]

        with self.assertRaises(Exception) as ctx:
            get_portfolio_tickers()
        self.assertIn("404", str(ctx.exception))

    @patch("app.services.ibkr.requests.get")
    def test_ibkr_returns_failure_status(self, mock_get):
        """IBKR returns 200 but with Status=Fail in XML."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_REFERENCE_RESPONSE_FAIL
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with self.assertRaises(RuntimeError) as ctx:
            get_portfolio_tickers()
        self.assertIn("Invalid token", str(ctx.exception))

    @patch("app.services.ibkr.requests.get")
    def test_ibkr_returns_success_without_reference_code(self, mock_get):
        """IBKR returns Status=Success but no ReferenceCode element."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_REFERENCE_RESPONSE_NO_CODE
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with self.assertRaises(RuntimeError) as ctx:
            get_portfolio_tickers()
        self.assertIn("ReferenceCode", str(ctx.exception))

    @patch("app.services.ibkr.time.sleep", return_value=None)
    @patch("app.services.ibkr.requests.get")
    def test_malformed_xml_in_report(self, mock_get, mock_sleep):
        """Step 1 succeeds but step 2 returns unparseable XML."""
        ref_response = MagicMock()
        ref_response.text = SAMPLE_REFERENCE_RESPONSE_OK
        ref_response.raise_for_status = MagicMock()

        bad_response = MagicMock()
        bad_response.text = MALFORMED_XML
        bad_response.raise_for_status = MagicMock()

        mock_get.side_effect = [ref_response, bad_response]

        with self.assertRaises(Exception):
            get_portfolio_tickers()


if __name__ == "__main__":
    unittest.main()
