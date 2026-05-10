# Risk/Sizing/Trailing Audit — 2026-05-09

**Scope reviewed:**
- `backend/src/risk/risk_manager.py` (§4-bis, §4-ter, §7-bis, `_compute_risk_usd`)
- `backend/src/risk/position_sizer.py` (`_stop_distance_usd`, `_max_position_pct_for_epic`, MIN_NOTIONAL floor)
- `backend/src/risk/kelly_sizer.py` (pip-aware path, notional floor)
- `backend/src/risk/trailing_stop_manager.py` (`_derive_tp_levels`, `register_migration`, `restore_state`, gap handling)
- `backend/src/risk/correlation_guard.py` (dynamic + static paths)
- `backend/tests/risk/test_risk_manager.py`, `test_trailing_stop_manager.py`, `test_trailing_stop_gap_scenarios.py`

---

## CRITICAL

None confirmed at wake-at-3am level after full read. The major invariants (§4-bis SL/TP pair rule, §7-bis cap-fallback approval, trailing midpoint formula) are correctly implemented.

---

## HIGH

**[`backend/tests/risk/test_risk_manager.py:24` + `risk_manager.py:340`] `_non_scalp_settings` mock leaves `min_signal_rr_threshold` unset — all autouse tests run §4-ter at threshold=1.0, not production 0.40**

- **What**: `_non_scalp_settings()` builds a `MagicMock()` and sets specific attributes but NOT `min_signal_rr_threshold`. On line 340 of `risk_manager.py`, `min_rr = float(_risk_settings.min_signal_rr_threshold)` calls `float()` on an unset MagicMock attribute. Python's `MagicMock` configures `__float__` to return `1.0` by default. Every test using the autouse `_disable_scalp` fixture therefore runs the R:R floor check with threshold=1.0 instead of the production 0.40.
- **Why it matters**: MR strategy signals target R:R ~0.75. A regression that moves the ATR-computed TP to produce R:R 0.85 would not be caught by tests because tests pass at 0.85 < 1.0, while production correctly accepts it. Test coverage of §4-ter is essentially zero for the correct threshold.
- **Suggested fix**: Add `s.min_signal_rr_threshold = 0.0` to `_non_scalp_settings`. Add dedicated tests at threshold=0.40.

---

## MEDIUM

**[`trailing_stop_manager.py:304`] `_derive_tp_levels` guard `take_profit > 0` is direction-unaware** — wrong-side TP for SELL passes guard, ladder fires immediate breakeven.

**[`correlation_guard.py:124`] Dynamic correlation path no floor on `size_multiplier`** — numpy float drift `abs_corr > 1.0` produces negative size, downstream rejection with misleading reason.

**[`trailing_stop_manager.py:385`] `restore_state` uses `lowest_price or entry_price`** — falsy `0.0` substituted with entry_price.

---

## LOW

- `risk_manager.py:562` — comment claims invariant violated by §6-bis epic_mult boost. Logic safe via `min()`, but comment misleading.
- `risk_manager.py:501` — floor skip when `risk_amount_usd == 0` silent.

---

## Coverage Gaps

1. §4-ter R:R floor — zero dedicated tests at production threshold 0.40
2. USDCHF/USDCAD pip-aware sizing — only USDJPY covered
3. `register_migration` `max_ladder_cycles=2` cap path — untested
4. Correlation matrix `abs_corr > 1.0` edge — untested
5. `restore_state` falsy-zero path — untested

---

## Summary

- 0 CRITICAL / 1 HIGH / 3 MEDIUM / 2 LOW
- 5 coverage gaps

Core invariants correctly implemented. HIGH finding is test-fidelity gap masking R:R floor regressions.
