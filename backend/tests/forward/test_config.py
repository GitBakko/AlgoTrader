from src.utils.config import get_settings


def test_experiment_account_settings_exist():
    s = get_settings()
    assert hasattr(s, "capital_experiment_account_id")
    assert hasattr(s, "forward_lab_notional_usd")
    assert hasattr(s, "forward_lab_daily_loss_limit_usd")
    assert s.forward_lab_notional_usd == 200.0


def test_orb_settings_defaults():
    from src.utils.config import get_settings
    s = get_settings()
    assert s.forward_lab_orb_or_window_min == 30
    assert s.forward_lab_orb_watch_end_et == "12:00"
    assert s.forward_lab_session_open_et == "09:30"
    assert s.forward_lab_eod_flatten_et == "16:45"
    assert s.forward_lab_orb_rvol_min == 1.5
    assert s.forward_lab_orb_top_k == 5
    assert s.forward_lab_orb_breakout_buffer == 0.0
    assert s.forward_lab_orb_stop_atr_mult == 1.0
