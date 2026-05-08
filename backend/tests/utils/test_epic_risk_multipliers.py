"""Tests for per-epic risk multiplier env parsing."""

from src.utils.config import Settings


def _make_settings(value: str) -> Settings:
    """Construct Settings with EPIC_RISK_MULTIPLIERS set, leaving the rest
    at defaults (env still drives required Capital.com creds, so we use
    the project `.env` for those)."""
    s = Settings()
    s.epic_risk_multipliers_str = value
    return s


class TestEpicRiskMultipliersParser:
    def test_empty_string_returns_empty_dict(self):
        assert _make_settings("").epic_risk_multipliers == {}

    def test_single_pair(self):
        assert _make_settings("TSLA=1.5").epic_risk_multipliers == {"TSLA": 1.5}

    def test_multiple_pairs(self):
        s = _make_settings("TSLA=1.5,USDJPY=1.5,DE40=0.0,BTCUSD=0.5")
        assert s.epic_risk_multipliers == {
            "TSLA": 1.5,
            "USDJPY": 1.5,
            "DE40": 0.0,
            "BTCUSD": 0.5,
        }

    def test_lowercase_epic_normalized_to_upper(self):
        assert _make_settings("tsla=1.5").epic_risk_multipliers == {"TSLA": 1.5}

    def test_whitespace_tolerated(self):
        s = _make_settings(" TSLA = 1.5 ,  USDJPY=1.5 ")
        assert s.epic_risk_multipliers == {"TSLA": 1.5, "USDJPY": 1.5}

    def test_malformed_token_skipped_not_raise(self):
        # Typos must NOT brick the system — silently drop bad tokens.
        s = _make_settings("TSLA=1.5,GARBAGE,DE40=notafloat,USDJPY=1.5")
        assert s.epic_risk_multipliers == {"TSLA": 1.5, "USDJPY": 1.5}

    def test_zero_multiplier_preserved(self):
        # 0.0 is the disable sentinel — must round-trip exactly.
        assert _make_settings("DE40=0.0").epic_risk_multipliers == {"DE40": 0.0}
