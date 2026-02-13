"""Tests for broker error parser — Italian-localized Capital.com error parsing."""

import pytest

from src.utils.broker_error_parser import ParsedBrokerError, parse_broker_error, _parse_timetable


class TestParsedBrokerError:
    """Test the ParsedBrokerError dataclass."""

    def test_to_dict(self):
        err = ParsedBrokerError(
            error_type="market_closed",
            summary="GOLD è attualmente chiuso",
            details="Orario: Lun-Ven 09:00-01:00",
            market_hours={"Mon": "09:00 -"},
            raw="Market currently closed",
        )
        d = err.to_dict()
        assert d["error_type"] == "market_closed"
        assert d["summary"] == "GOLD è attualmente chiuso"
        assert d["market_hours"] == {"Mon": "09:00 -"}
        assert d["raw"] == "Market currently closed"


class TestParseMarketClosed:
    """Test market_closed error type."""

    def test_currently_closed_simple(self):
        result = parse_broker_error("Market is currently closed", epic="GOLD")
        assert result.error_type == "market_closed"
        assert "GOLD" in result.summary
        assert "chiuso" in result.summary

    def test_with_timetable(self):
        msg = (
            "Market is currently closed. "
            "Timetable in place: UTC; Mon 09:00 -; Tue - 01:00, 09:00 -; "
            "Wed - 01:00, 09:00 -; Thu - 01:00, 09:00 -; Fri - 01:00, 09:00 -."
        )
        result = parse_broker_error(msg, epic="XAUUSD")
        assert result.error_type == "market_closed"
        assert result.details is not None
        assert "Orario" in result.details
        assert result.market_hours is not None
        assert "Mon" in result.market_hours

    def test_no_epic_uses_asset_label(self):
        result = parse_broker_error("currently closed")
        assert result.error_type == "market_closed"
        assert "Asset" in result.summary


class TestParseInsufficientFunds:
    """Test insufficient_funds error type."""

    def test_basic(self):
        result = parse_broker_error("Insufficient funds for trade", epic="BTCUSD")
        assert result.error_type == "insufficient_funds"
        assert "BTCUSD" in result.summary
        assert "insufficienti" in result.summary.lower()

    def test_case_insensitive(self):
        result = parse_broker_error("INSUFFICIENT FUND balance")
        assert result.error_type == "insufficient_funds"


class TestParseRateLimit:
    """Test rate_limit error type."""

    def test_basic(self):
        result = parse_broker_error("Rate limit exceeded, try again later")
        assert result.error_type == "rate_limit"
        assert "Limite" in result.summary
        assert "richieste" in result.summary.lower()

    def test_case_insensitive(self):
        result = parse_broker_error("API RATE LIMIT reached")
        assert result.error_type == "rate_limit"


class TestParseMinSize:
    """Test min_size error type."""

    def test_with_size_value(self):
        result = parse_broker_error("Minimum position size is 0.01", epic="US500")
        assert result.error_type == "min_size"
        assert "US500" in result.summary
        assert "0.01" in result.summary

    def test_without_size_value(self):
        result = parse_broker_error("Below minimum size allowed")
        assert result.error_type == "min_size"
        assert "piccola" in result.summary.lower()


class TestParseInvalidMarket:
    """Test invalid_market error type."""

    def test_invalid_market(self):
        result = parse_broker_error("Invalid market identifier", epic="FAKEMKT")
        assert result.error_type == "invalid_market"
        assert "FAKEMKT" in result.summary

    def test_invalid_epic(self):
        result = parse_broker_error("Invalid epic provided")
        assert result.error_type == "invalid_market"


class TestParseMaxPositions:
    """Test max_positions error type."""

    def test_basic(self):
        result = parse_broker_error("Maximum number of positions reached")
        assert result.error_type == "max_positions"
        assert "massimo" in result.summary.lower()
        assert result.details is not None


class TestParseRejected:
    """Test rejected error type."""

    def test_with_reason(self):
        result = parse_broker_error("Rejected. Margin call in progress", epic="GOLD")
        assert result.error_type == "rejected"
        assert "GOLD" in result.summary
        assert "rifiutato" in result.summary.lower()
        assert "Margin call" in result.details

    def test_without_reason(self):
        result = parse_broker_error("Order rejected")
        assert result.error_type == "rejected"
        assert result.details is None

    def test_long_reason_truncated(self):
        long_reason = "A" * 300
        result = parse_broker_error(f"Rejected. {long_reason}")
        assert result.error_type == "rejected"
        assert len(result.details) <= 200


class TestParseUnknown:
    """Test unknown/fallback error type."""

    def test_unknown_error(self):
        result = parse_broker_error("Something completely unexpected happened")
        assert result.error_type == "unknown"
        assert "Errore broker" in result.summary

    def test_short_unknown(self):
        result = parse_broker_error("Oops")
        assert result.error_type == "unknown"
        assert result.details is None  # message too short for details

    def test_long_unknown_has_details(self):
        long_msg = "X" * 120
        result = parse_broker_error(long_msg, epic="GOLD")
        assert result.error_type == "unknown"
        assert result.details is not None
        assert result.details.endswith("...")


class TestParseTimetable:
    """Test _parse_timetable helper."""

    def test_no_timetable(self):
        summary, hours = _parse_timetable("No timetable here")
        assert summary is None
        assert hours is None

    def test_full_timetable(self):
        raw = (
            "Timetable in place: UTC; Mon 09:00 -; Tue - 01:00, 09:00 -; "
            "Wed - 01:00, 09:00 -; Thu - 01:00, 09:00 -; Fri - 01:00, 09:00 -."
        )
        summary, hours = _parse_timetable(raw)
        assert summary is not None
        assert hours is not None
        assert "Mon" in hours
        assert "Fri" in hours
        # Italian day names in summary
        assert "Lun" in summary or "Mar" in summary

    def test_empty_after_timetable_marker(self):
        raw = "Timetable in place: "
        summary, hours = _parse_timetable(raw)
        # Empty parts → None
        assert summary is None or hours is None

    def test_timetable_with_unrecognized_format(self):
        raw = "Timetable in place: some weird format without days"
        summary, hours = _parse_timetable(raw)
        assert hours is None  # no days found
        assert summary is not None  # raw timetable returned
