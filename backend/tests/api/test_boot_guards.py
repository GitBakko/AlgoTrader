"""Regression: two silent boot misconfigurations must hard-fail (audit M1.8).

1. Non-demo settings with a default/weak SECRET_KEY would mint forgeable JWTs
   guarding the kill-switch.
2. EXECUTION_MODE=LIVE + USE_DEMO=true silently left the throwaway PAPER
   engine simulating fills while the dashboard showed trading activity.

Note: Settings uses pydantic-settings v2 with Field(alias=...) where aliases
are the uppercase env-var names (USE_DEMO, SECRET_KEY, AUTH_REQUIRED, etc.).
Required fields (no default) must also be supplied: CAPITAL_DEMO_API_KEY,
CAPITAL_DEMO_EMAIL, CAPITAL_DEMO_PASSWORD.
"""

import inspect
import re

import pytest
from pydantic import ValidationError

# Minimal required fields shared by all Settings-constructing tests.
_REQUIRED = {
    "CAPITAL_DEMO_API_KEY": "test-key",
    "CAPITAL_DEMO_EMAIL": "test@example.com",
    "CAPITAL_DEMO_PASSWORD": "test-password",
}

_STRONG_KEY = "ops-provisioned-key-0123456789abcdef0123456789abcdef0123456789ab"


class TestSecretKeyGuard:
    @pytest.mark.parametrize(
        "bad_key",
        [
            "dev_secret_key_change_in_production",  # exact default sentinel
            "",  # empty
            "short-key-under-32-chars",  # < 32 chars
        ],
    )
    def test_weak_secret_key_rejected_when_not_demo(self, bad_key):
        from src.utils.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                **_REQUIRED,
                USE_DEMO=False,
                SECRET_KEY=bad_key,
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
            SECRET_KEY=_STRONG_KEY,
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

    def test_unknown_mode_raises(self):
        """A typo like EXECUTION_MODE=LIV must not fall through to silent PAPER."""
        from src.api.main import _validate_execution_mode_request

        with pytest.raises(RuntimeError, match="unknown EXECUTION_MODE 'LIV'"):
            _validate_execution_mode_request(desired="LIV", use_demo=False)

    @pytest.mark.parametrize(
        "desired,use_demo",
        [("DEMO", True), ("LIVE", False), ("PAPER", True), ("PAPER", False)],
    )
    def test_coherent_combos_pass(self, desired, use_demo):
        from src.api.main import _validate_execution_mode_request

        _validate_execution_mode_request(desired=desired, use_demo=use_demo)

    def test_lifespan_guard_reads_settings_not_app_state(self):
        """Wiring pin: app.state._desired_execution_mode is written only by
        init_services, which runs AFTER the guard call in lifespan — a
        getattr(app.state, ...) read there always saw the "PAPER" default and
        the guard was dead code. The call site must read
        settings.execution_mode directly (same source init_services stores).
        """
        from src.api import main

        src = inspect.getsource(main.lifespan)
        call = re.search(
            r"_validate_execution_mode_request\((.*?)\)\s*\n",
            src,
            re.DOTALL,
        )
        assert call, "lifespan no longer calls _validate_execution_mode_request"
        args = call.group(1)
        assert "settings.execution_mode" in args, (
            "guard call site must read settings.execution_mode directly; "
            "app.state._desired_execution_mode is not yet populated at this "
            f"point in lifespan. Found args: {args!r}"
        )
        assert "_desired_execution_mode" not in args
