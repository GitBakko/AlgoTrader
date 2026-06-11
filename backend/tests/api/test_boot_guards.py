"""Regression: two silent boot misconfigurations must hard-fail (audit M1.8).

1. Non-demo settings with the default SECRET_KEY would mint forgeable JWTs
   guarding the kill-switch.
2. EXECUTION_MODE=LIVE + USE_DEMO=true silently left the throwaway PAPER
   engine simulating fills while the dashboard showed trading activity.

Note: Settings uses pydantic-settings v2 with Field(alias=...) where aliases
are the uppercase env-var names (USE_DEMO, SECRET_KEY, AUTH_REQUIRED, etc.).
Required fields (no default) must also be supplied: CAPITAL_DEMO_API_KEY,
CAPITAL_DEMO_EMAIL, CAPITAL_DEMO_PASSWORD.
"""

import pytest

# Minimal required fields shared by all Settings-constructing tests.
_REQUIRED = {
    "CAPITAL_DEMO_API_KEY": "test-key",
    "CAPITAL_DEMO_EMAIL": "test@example.com",
    "CAPITAL_DEMO_PASSWORD": "test-password",
}


class TestSecretKeyGuard:
    def test_default_secret_key_rejected_when_not_demo(self):
        from src.utils.config import Settings

        with pytest.raises(Exception) as exc_info:
            Settings(
                **_REQUIRED,
                USE_DEMO=False,
                SECRET_KEY="dev_secret_key_change_in_production",
                AUTH_REQUIRED=True,
                _env_file=None,
            )
        assert "SECRET_KEY" in str(exc_info.value)

    def test_default_secret_key_only_warns_in_demo(self):
        from src.utils.config import Settings

        s = Settings(
            **_REQUIRED,
            USE_DEMO=True,
            SECRET_KEY="dev_secret_key_change_in_production",
            _env_file=None,
        )
        assert s.use_demo is True

    def test_custom_secret_key_fine_outside_demo(self):
        from src.utils.config import Settings

        s = Settings(
            **_REQUIRED,
            USE_DEMO=False,
            SECRET_KEY="a-real-64-char-key-set-by-ops",
            AUTH_REQUIRED=True,
            _env_file=None,
        )
        assert s.use_demo is False


class TestExecutionModeGuard:
    @pytest.mark.parametrize(
        "desired,use_demo",
        [("LIVE", True), ("DEMO", False)],
    )
    def test_mismatch_raises(self, desired, use_demo):
        from src.api.main import _validate_execution_mode_request

        with pytest.raises(RuntimeError, match="EXECUTION_MODE"):
            _validate_execution_mode_request(desired=desired, use_demo=use_demo)

    @pytest.mark.parametrize(
        "desired,use_demo",
        [("DEMO", True), ("LIVE", False), ("PAPER", True), ("PAPER", False)],
    )
    def test_coherent_combos_pass(self, desired, use_demo):
        from src.api.main import _validate_execution_mode_request

        _validate_execution_mode_request(desired=desired, use_demo=use_demo)
