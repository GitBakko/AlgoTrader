# MANTIS-EVOLUTION: RL Reward Functions
"""Reward functions for the MANTIS RL trading environment."""

from __future__ import annotations

import numpy as np

from src.rl.schemas import EnvState, RLConfig


class MantisRewardCalculator:
    """Calculates rewards for RL environment steps."""

    def __init__(self, config: RLConfig | None = None):
        self.config = config or RLConfig()

    def sharpe_reward(self, state: EnvState) -> float:
        """
        Reward based on incremental Sharpe ratio.
        Penalizes high-volatility P&L.
        """
        returns = state.returns_history
        if len(returns) < 2:
            return 0.0
        mean_ret = np.mean(returns)
        std_ret = np.std(returns, ddof=1)
        if std_ret < 1e-8:
            return mean_ret * 10  # low vol = good, scale up
        sharpe = mean_ret / std_ret
        return float(np.clip(sharpe, -2.0, 2.0))  # clip to prevent extreme values

    def scalping_reward(self, state: EnvState) -> float:
        """
        Reward optimized for scalping:
        + Bonus for quick profits (< target_hold_candles)
        + Bonus for high win rate
        - Penalty for drawdown > max_drawdown_pct
        - Penalty for overtrading (> max_trades_per_session)
        - Penalty for holding in HIGH/EXTREME volatility
        """
        reward = 0.0

        # Base: current profit if in position
        reward += state.current_profit * 10  # scale up small fractions

        # Quick profit bonus
        if state.current_profit > 0 and state.trade_duration < self.config.target_hold_candles:
            reward += 0.5  # bonus for being profitable quickly

        # Win rate bonus (if enough trades)
        if state.total_trades >= 3:
            win_rate = state.wins / state.total_trades
            reward += (win_rate - 0.5) * 2  # positive if WR > 50%

        # Drawdown penalty
        if state.max_drawdown > self.config.max_drawdown_pct:
            excess = state.max_drawdown - self.config.max_drawdown_pct
            reward -= excess * 100  # strong penalty

        # Overtrading penalty
        if state.total_trades > self.config.max_trades_per_session:
            reward -= (state.total_trades - self.config.max_trades_per_session) * 0.5

        # Volatility penalty (holding in high vol = risky)
        if state.position != 0 and state.volatility_regime >= 2:  # HIGH or EXTREME
            reward -= 0.3 * (state.volatility_regime - 1)

        return float(reward)

    def risk_adjusted_reward(self, state: EnvState) -> float:
        """
        Reward scaled by Kelly-criterion-like edge estimation.
        Uses win rate and avg win/loss to estimate edge.
        """
        if state.total_trades < 2:
            return 0.0

        win_rate = state.wins / state.total_trades if state.total_trades > 0 else 0.0

        wins = [r for r in state.returns_history if r > 0]
        losses = [r for r in state.returns_history if r < 0]

        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = abs(np.mean(losses)) if losses else 1e-8

        # Kelly fraction (simplified)
        if avg_loss > 0:
            win_loss_ratio = avg_win / avg_loss
            kelly = win_rate - (1 - win_rate) / win_loss_ratio if win_loss_ratio > 0 else 0.0
        else:
            kelly = win_rate

        # Reward = current profit scaled by kelly edge
        reward = state.current_profit * (1 + kelly) * 5

        # Bonus for positive edge
        if kelly > 0:
            reward += kelly * 2
        else:
            reward -= 0.5  # penalty for negative edge

        return float(np.clip(reward, -3.0, 3.0))

    def composite_reward(self, state: EnvState, weights: dict[str, float] | None = None) -> float:
        """
        Weighted combination of all 3 reward functions.
        Default: 0.4 scalping + 0.4 sharpe + 0.2 risk_adjusted
        """
        w = weights or self.config.reward_weights
        w_scalp = w.get("scalping", 0.0)
        w_sharpe = w.get("sharpe", 0.0)
        w_risk = w.get("risk_adjusted", 0.0)

        total = w_scalp + w_sharpe + w_risk
        if total < 1e-8:
            return 0.0

        reward = (
            self.scalping_reward(state) * w_scalp
            + self.sharpe_reward(state) * w_sharpe
            + self.risk_adjusted_reward(state) * w_risk
        ) / total

        return float(reward)

    def xgb_marginal_reward(self, state: EnvState) -> float:
        """
        Phase 5-bis reward shaping.

        Reward = (PPO realised step P&L) - (XGBoost baseline step P&L),
        scaled by `config.xgb_marginal_scale`.

        Encourages the agent to add marginal value over the XGBoost
        director rather than learning to trade in isolation.  When the
        baseline P&L stream is zero (standalone training) this falls
        back to scaled current_profit, equivalent to a smaller-magnitude
        scalping reward.
        """
        scale = float(getattr(self.config, "xgb_marginal_scale", 5.0))

        # Realised step P&L for the agent.  When a trade just closed in
        # this step the last entry of returns_history is non-zero; while
        # holding open we use unrealised current_profit as a smoothed
        # proxy.
        agent_step_pnl = (
            state.returns_history[-1]
            if state.returns_history and state.trade_duration == 0
            else state.current_profit
        )
        baseline_step_pnl = float(state.xgb_step_pnl)

        marginal = agent_step_pnl - baseline_step_pnl
        reward = marginal * scale

        # Soft drawdown penalty so the marginal reward can't run away.
        if state.max_drawdown > self.config.max_drawdown_pct:
            excess = state.max_drawdown - self.config.max_drawdown_pct
            reward -= excess * 50.0

        return float(np.clip(reward, -3.0, 3.0))
