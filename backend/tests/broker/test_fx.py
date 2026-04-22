"""Unit tests for the fail-loud FX converter.

The converter MUST:
  - pass through when source == target currency (after normalization),
  - use the FRED series when a pair is mapped, inverting when required,
  - raise FxUnavailableError — never return the unconverted value — when
    the FRED lookup is unavailable or the pair is unmapped.

This module is part of the "FX silently propagated" audit finding and the
fail-loud contract is the whole point; do NOT relax the assertions below
to get a green build without understanding WHY the rate is missing.
"""

from __future__ import annotations

import pytest

from src.broker.fx import (
    FX_PAIR_SERIES,
    FxConverter,
    FxUnavailableError,
    normalize_currency,
)


class _StubFred:
    """Minimal stub emulating FREDClient.fetch_single(series_id)."""

    def __init__(self, mapping: dict[str, float | None], raises: Exception | None = None):
        self._mapping = mapping
        self._raises = raises
        self.calls: list[str] = []

    async def fetch_single(self, series_id: str):
        self.calls.append(series_id)
        if self._raises is not None:
            raise self._raises
        return self._mapping.get(series_id)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("USDd", "USD"),
        ("usd", "USD"),
        ("USD", "USD"),
        (" eur ", "EUR"),
        ("GBPd", "GBP"),
        (None, ""),
        ("", ""),
        ("USD-d", "USD"),
    ],
)
def test_normalize_currency(raw, expected):
    assert normalize_currency(raw) == expected


async def test_same_currency_passthrough():
    fx = FxConverter(fred_client=_StubFred({}))
    assert await fx.convert(29.28, "USDd", "USD") == 29.28


async def test_eur_to_usd_uses_dexuseu_as_is():
    stub = _StubFred({"DEXUSEU": 1.10})
    fx = FxConverter(fred_client=stub)
    got = await fx.convert(100.0, "EUR", "USD")
    assert got == pytest.approx(110.0)
    assert stub.calls == ["DEXUSEU"]


async def test_usd_to_eur_inverts_dexuseu():
    stub = _StubFred({"DEXUSEU": 1.25})
    fx = FxConverter(fred_client=stub)
    got = await fx.convert(100.0, "USD", "EUR")
    assert got == pytest.approx(80.0)  # 100 / 1.25
    assert stub.calls == ["DEXUSEU"]


async def test_unmapped_pair_raises_loud():
    fx = FxConverter(fred_client=_StubFred({}))
    with pytest.raises(FxUnavailableError):
        await fx.convert(10.0, "XAU", "USD")


async def test_missing_rate_raises_loud():
    fx = FxConverter(fred_client=_StubFred({"DEXUSEU": None}))
    with pytest.raises(FxUnavailableError):
        await fx.convert(10.0, "EUR", "USD")


async def test_fred_exception_propagates_as_fx_unavailable():
    boom = RuntimeError("network unreachable")
    fx = FxConverter(fred_client=_StubFred({}, raises=boom))
    with pytest.raises(FxUnavailableError) as excinfo:
        await fx.convert(10.0, "EUR", "USD")
    assert "network unreachable" in str(excinfo.value)


async def test_rate_is_cached_after_first_fetch():
    stub = _StubFred({"DEXUSEU": 1.10})
    fx = FxConverter(fred_client=stub)
    await fx.convert(1.0, "EUR", "USD")
    await fx.convert(1.0, "EUR", "USD")
    await fx.convert(1.0, "EUR", "USD")
    assert stub.calls == ["DEXUSEU"], (
        "FRED was called more than once; rate should have been cached"
    )


def test_every_declared_pair_covers_both_directions():
    """If we register a pair, we must also register its inverse."""
    for (a, b), (_series, _invert) in FX_PAIR_SERIES.items():
        assert (b, a) in FX_PAIR_SERIES, (
            f"Missing inverse FX pair {b}->{a}; v2 close detector assumes "
            f"symmetric coverage so either direction can be converted."
        )


def test_pairs_share_series_between_directions():
    """The two directions of the same pair must share one FRED series id
    with opposite invert flags. Prevents typos drifting the pair over time.
    """
    for (a, b), (series, invert) in FX_PAIR_SERIES.items():
        rev_series, rev_invert = FX_PAIR_SERIES[(b, a)]
        assert series == rev_series, (
            f"Series mismatch: {a}->{b} uses {series}, {b}->{a} uses {rev_series}"
        )
        assert invert != rev_invert, (
            f"Both {a}->{b} and {b}->{a} have invert={invert}; one of them must invert"
        )
