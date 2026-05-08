"""
Test suite for Phase 12: Portfolio Expansion (12 new EPICs).
Verifies all configuration updates are correct.
"""

from src.api.routers.markets import SUPPORTED_MARKETS
from src.api.routers.models import _MODEL_REGISTRY
from src.api.routers.strategy import SUPPORTED_EPICS
from src.broker.client import BROKER_TO_EPIC, EPIC_TO_BROKER
from src.features.asset_config import ASSET_FEATURE_CONFIGS, get_asset_config
from src.models.prediction_service import PredictionService

# Expected 12 new EPICs
NEW_EPICS = [
    "SOLUSD",
    "ETHUSD",
    "BNBUSD",
    "DOGUSD",
    "DASHUSD",
    "ICPUSD",
    "NATGAS",
    "COPPER",
    "PLATINUM",
    "GBPUSD",
    "USDJPY",
    "NAS100",
]

# Expected broker mappings (only 3 need translation)
EXPECTED_MAPPINGS = {
    "DOGUSD": "DOGEUSD",
    "NATGAS": "NATURALGAS",
    "NAS100": "QTEC",
}


class TestPortfolioExpansion:
    """Verify Phase 12 portfolio expansion to 21 assets."""

    def test_markets_count(self):
        """Markets router should have 21 market infos."""
        assert len(SUPPORTED_MARKETS) == 21, f"Expected 21 markets, got {len(SUPPORTED_MARKETS)}"

    def test_new_markets_present(self):
        """All 12 new EPICs should be in SUPPORTED_MARKETS."""
        market_epics = [m.epic for m in SUPPORTED_MARKETS]
        for epic in NEW_EPICS:
            assert epic in market_epics, f"New EPIC {epic} missing from SUPPORTED_MARKETS"

    def test_strategy_epics_count(self):
        """Strategy router should have 29 EPICs (Phase 12 + Phase 14 stocks/forex)."""
        assert len(SUPPORTED_EPICS) == 29, f"Expected 29 strategy EPICs, got {len(SUPPORTED_EPICS)}"

    def test_new_strategy_epics_present(self):
        """All 12 new EPICs should be in SUPPORTED_EPICS."""
        for epic in NEW_EPICS:
            assert epic in SUPPORTED_EPICS, f"New EPIC {epic} missing from SUPPORTED_EPICS"

    def test_model_registry_count(self):
        """Model registry should have 21 model entries."""
        assert len(_MODEL_REGISTRY) == 21, f"Expected 21 models, got {len(_MODEL_REGISTRY)}"

    def test_new_models_present(self):
        """All 12 new EPICs should have model registry entries."""
        model_epics = [m["epic"] for m in _MODEL_REGISTRY]
        for epic in NEW_EPICS:
            assert epic in model_epics, f"New EPIC {epic} missing from _MODEL_REGISTRY"

    def test_feature_configs_count(self):
        """Asset feature configs should have 29 entries (Phase 12 + Phase 14 candidates)."""
        assert (
            len(ASSET_FEATURE_CONFIGS) == 29
        ), f"Expected 29 feature configs, got {len(ASSET_FEATURE_CONFIGS)}"

    def test_new_feature_configs_present(self):
        """All 12 new EPICs should have feature configs."""
        for epic in NEW_EPICS:
            assert (
                epic in ASSET_FEATURE_CONFIGS
            ), f"New EPIC {epic} missing from ASSET_FEATURE_CONFIGS"

    def test_feature_config_structure(self):
        """Each new EPIC should have valid AssetFeatureConfig."""
        for epic in NEW_EPICS:
            config = get_asset_config(epic)
            assert config.epic == epic
            assert config.primary_timeframe in ["1h", "4h", "1d"]
            assert isinstance(config.additional_timeframes, list)
            assert len(config.features) > 0

    def test_active_epics_count(self):
        """PredictionService.ACTIVE_EPICS should have 21.

        Composition: 13 surviving Phase 0/Phase 12 (XAUUSD, BTCUSD, US500,
        WTIUSD, NVDA, TSLA, DE40, SOLUSD, ETHUSD, BNBUSD, COPPER, PLATINUM,
        USDJPY) + 2 Phase 14 forex (USDCHF, USDCAD) + 6 Phase 14 stocks
        (AAPL/MSFT/GOOGL/AMZN/META/AMD) — promoted 2026-05-08 after
        Capital.com history backfill (~17.5 bars/cal-day density).
        """
        assert (
            len(PredictionService.ACTIVE_EPICS) == 21
        ), f"Expected 21 active EPICs, got {len(PredictionService.ACTIVE_EPICS)}"

    def test_new_active_epics_present(self):
        """Surviving new EPICs should be in PredictionService.ACTIVE_EPICS."""
        surviving_new = ["SOLUSD", "ETHUSD", "BNBUSD", "PLATINUM"]
        for epic in surviving_new:
            assert (
                epic in PredictionService.ACTIVE_EPICS
            ), f"New EPIC {epic} missing from ACTIVE_EPICS"

    def test_eurusd_excluded(self):
        """EURUSD should be excluded from ACTIVE_EPICS (poor OOS performance)."""
        assert "EURUSD" in PredictionService.EXCLUDED_EPICS
        assert "EURUSD" not in PredictionService.ACTIVE_EPICS

    def test_broker_mappings(self):
        """Verify 3 critical EPIC broker name mappings."""
        for internal, broker in EXPECTED_MAPPINGS.items():
            assert (
                EPIC_TO_BROKER.get(internal) == broker
            ), f"EPIC {internal} should map to {broker}, got {EPIC_TO_BROKER.get(internal)}"

    def test_reverse_broker_mappings(self):
        """Verify reverse broker mappings (BROKER_TO_EPIC)."""
        for internal, broker in EXPECTED_MAPPINGS.items():
            assert BROKER_TO_EPIC.get(broker) == internal, (
                f"Broker {broker} should reverse-map to {internal}, "
                f"got {BROKER_TO_EPIC.get(broker)}"
            )

    def test_no_duplicates_in_markets(self):
        """No duplicate EPICs in SUPPORTED_MARKETS."""
        epics = [m.epic for m in SUPPORTED_MARKETS]
        assert len(epics) == len(set(epics)), "Duplicate EPICs in SUPPORTED_MARKETS"

    def test_no_duplicates_in_strategy(self):
        """No duplicate EPICs in SUPPORTED_EPICS."""
        assert len(SUPPORTED_EPICS) == len(
            set(SUPPORTED_EPICS)
        ), "Duplicate EPICs in SUPPORTED_EPICS"

    def test_crypto_24_7_configs(self):
        """Verify crypto assets (6 new) have expected config patterns."""
        crypto_epics = ["SOLUSD", "ETHUSD", "BNBUSD", "DOGUSD", "DASHUSD", "ICPUSD"]
        for epic in crypto_epics:
            config = get_asset_config(epic)
            # Crypto should have high volatility periods (hvol_period=20)
            assert (
                config.technical_params.get("hvol_period") == 20
            ), f"Crypto {epic} should have hvol_period=20"

    def test_forex_configs(self):
        """Verify forex assets (2 new) have expected config patterns."""
        forex_epics = ["GBPUSD", "USDJPY"]
        for epic in forex_epics:
            config = get_asset_config(epic)
            # Forex should have standard RSI period
            assert (
                config.technical_params.get("rsi_period") == 14
            ), f"Forex {epic} should have rsi_period=14"

    def test_commodity_configs(self):
        """Verify commodity assets (3 new) have expected config patterns."""
        commodity_epics = ["NATGAS", "COPPER", "PLATINUM"]
        for epic in commodity_epics:
            config = get_asset_config(epic)
            # Commodities should have gold correlation feature (disabled placeholder)
            features = [f.name for f in config.features]
            assert (
                "gold_correlation" in features
            ), f"Commodity {epic} should have gold_correlation feature"

    def test_index_config(self):
        """Verify index asset (NAS100) has expected config patterns."""
        config = get_asset_config("NAS100")
        # NAS100 should have S&P 500 correlation feature
        features = [f.name for f in config.features]
        assert "sp500_correlation" in features, "NAS100 should have sp500_correlation feature"
        # High volatility index
        assert config.technical_params.get("hvol_period") == 20


# Integration test (requires imports to succeed)
def test_all_imports_valid():
    """Verify all Phase 12 modules import without errors."""
    from src.api.main import app
    from src.features.asset_config import ASSET_FEATURE_CONFIGS

    # If we reach here, all imports succeeded
    assert app is not None
    assert len(ASSET_FEATURE_CONFIGS) == 29
