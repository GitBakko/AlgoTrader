"""Regression: the min-size retry success path must produce the same
post-fill side effects as the main success path (audit M1.5b). On HEAD it
is a diverged copy missing stops-align, _level_deviations, the SUSPICIOUS
LEVELS check, EXECUTED trade-log rows and the signal-audit link.

Contract: both branches call the SAME _finalize_entry method (source-
inspection guard, repo precedent: test_strategy_3_fuzzy_match_source_is_deleted)."""

import inspect

from src.trading.paper_loop import PaperTradingLoop


def test_finalize_entry_exists_and_both_branches_use_it():
    assert hasattr(PaperTradingLoop, "_finalize_entry")
    src = inspect.getsource(PaperTradingLoop._process_epic)
    assert src.count("_finalize_entry(") >= 2, (
        "both the main success branch and the min-size retry success branch "
        "must delegate to _finalize_entry"
    )
    finalize_src = inspect.getsource(PaperTradingLoop._finalize_entry)
    assert "SUSPICIOUS" in finalize_src
    assert src.count("SUSPICIOUS") == 0


def test_finalize_entry_contains_the_load_bearing_side_effects():
    finalize_src = inspect.getsource(PaperTradingLoop._finalize_entry)
    for marker in (
        "_level_deviations",
        "_register_intra_tick_open",
        "update_stops",
        "_persist_position_open",
        "log_execution",
        "mark_as_executed",
        "record_trade_execution",
        "register_position",
    ):
        assert marker in finalize_src, f"missing post-fill side effect: {marker}"
