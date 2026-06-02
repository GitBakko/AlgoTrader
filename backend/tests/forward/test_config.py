from src.utils.config import get_settings


def test_experiment_account_settings_exist():
    s = get_settings()
    assert hasattr(s, "capital_experiment_account_id")
    assert hasattr(s, "forward_lab_notional_usd")
    assert hasattr(s, "forward_lab_daily_loss_limit_usd")
    assert s.forward_lab_notional_usd == 200.0
