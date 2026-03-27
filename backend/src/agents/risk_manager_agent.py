# MANTIS-EVOLUTION: Risk Manager Agent
"""
RiskManagerAgent — the risk management specialist in the MANTIS AI
multi-agent trading system.

Two analysis paths:
1. **LLM path** (default): calls Claude via base class ``_call_llm()`` for
   nuanced portfolio and market risk reasoning.
2. **Heuristic fallback**: pure computation from MarketContext fields, used
   when the LLM path fails (API outage, rate-limit, import error) or is
   disabled.

The heuristic path evaluates five weighted risk components:
  - Volatility risk   (ATR%)           — 30% weight
  - RSI extreme risk  (distance from 50) — 15% weight
  - Position exposure (open positions)  — 25% weight
  - ADX chop risk     (low ADX = choppy) — 15% weight
  - Equity exposure   (simplified)      — 15% weight

**Veto power**: if risk_score > RISK_BLOCK_THRESHOLD (0.8), ``blocking`` is
set to ``True``, which forces a HOLD outcome in the orchestrator regardless
of any bullish/bearish signals from other agents.
"""

from __future__ import annotations

from loguru import logger

from src.agents.base_agent import MantisBaseAgent
from src.agents.schemas import AgentRole, MarketContext, RiskReport


class RiskManagerAgent(MantisBaseAgent):
    """
    Risk management agent for MANTIS AI.

    Produces a ``RiskReport`` by either:
    - Calling Claude (LLM path) for nuanced risk reasoning, or
    - Computing a heuristic risk assessment directly from ``MarketContext``
      fields (fallback).

    Has **veto power**: risk_score > 0.8 sets ``blocking=True``, which the
    orchestrator must honour by forcing a HOLD decision.
    """

    role = AgentRole.RISK
    output_schema = RiskReport

    # Blocking threshold: risk_score strictly greater than this → veto
    RISK_BLOCK_THRESHOLD: float = 0.8

    # ------------------------------------------------------------------
    # Abstract interface implementation
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        """Return the role-specific system prompt for risk analysis."""
        return (
            "You are an expert risk manager for an algorithmic trading fund specialising in "
            "crypto, forex, and commodities. You have deep knowledge of volatility regimes, "
            "portfolio exposure limits, drawdown management, and liquidity risk.\n\n"
            "Your task is to analyse the provided market context and produce a structured "
            "risk report. You must:\n"
            "1. Assign a risk_score from 0.0 (safe) to 1.0 (extreme risk)\n"
            "2. Classify volatility regime: LOW, MEDIUM, HIGH, or EXTREME based on ATR%\n"
            "3. Set blocking=True if risk_score > 0.8 — this vetoes all trade signals\n"
            "4. Recommend a maximum position size (% of equity) inversely proportional to risk\n"
            "5. Recommend a stop-loss distance as a percentage\n"
            "6. Score market liquidity from 0.0 (illiquid) to 1.0 (highly liquid)\n"
            "7. Provide a concise rationale summarising the key risk factors\n\n"
            "Respond ONLY with valid JSON matching the requested schema. "
            "Do not include any explanation outside the JSON object."
        )

    def _build_user_message(self, context: MarketContext) -> str:
        """Format the MarketContext into a structured risk analysis prompt for Claude."""
        features = context.features
        atr_pct = (context.atr / context.current_price * 100) if context.current_price > 0 else 0.0

        lines = [
            f"## Risk Analysis Request: {context.epic}",
            "",
            f"**Asset**: {context.epic}",
            f"**Timeframe**: {context.timeframe}",
            f"**Current Price**: {context.current_price:.6g}",
            f"**ATR**: {context.atr:.6g}  ({atr_pct:.2f}% of price)",
            f"**Open Positions**: {context.open_positions}",
            f"**Portfolio Equity**: {context.equity:.2f}",
            f"**Market Regime**: {context.regime or 'UNKNOWN'}",
            "",
            "### Key Risk Indicators",
        ]

        risk_keys = ("rsi_14", "adx_14", "bb_width", "volume", "volume_sma")
        if features:
            for key in risk_keys:
                val = features.get(key)
                if val is not None:
                    formatted = f"{val:.6g}" if isinstance(val, (int, float)) else str(val)
                    lines.append(f"  - {key}: {formatted}")
            # Any other features
            other = {k: v for k, v in features.items() if k not in risk_keys}
            if other:
                lines.append("")
                lines.append("### Additional Features")
                for k, v in list(other.items())[:20]:  # cap to avoid token overflow
                    formatted = (
                        f"{v:.6g}" if isinstance(v, (int, float)) and v is not None else str(v)
                    )
                    lines.append(f"  - {k}: {formatted}")
        else:
            lines.append("  *(no feature data available — use ATR and position data only)*")

        lines += [
            "",
            "### Task",
            f"Assess risk for {context.epic} at {context.current_price:.6g}.",
            f"ATR is {atr_pct:.2f}% of price — use this to classify volatility regime.",
            f"There are {context.open_positions} open positions against equity of {context.equity:.2f}.",
            "Set blocking=True if overall risk_score exceeds 0.8.",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public entry point — LLM first, heuristic fallback
    # ------------------------------------------------------------------

    async def analyze(self, context: MarketContext) -> RiskReport | None:
        """
        Try the LLM path first; fall back to heuristic analysis on any failure.

        Unlike the base ``analyze()`` which returns ``None`` on failure, this
        subclass ALWAYS returns a ``RiskReport`` — the heuristic path
        guarantees a result even when Claude is unreachable.

        The ``blocking`` flag is the key output: if ``True``, the orchestrator
        must force a HOLD and not open any new position.
        """
        result = await super().analyze(context)
        if result is not None:
            return result
        logger.info(f"[RISK] LLM path unavailable for {context.epic}, " "using heuristic fallback.")
        return self._heuristic_analyze(context)

    # ------------------------------------------------------------------
    # Heuristic analysis — zero external dependencies
    # ------------------------------------------------------------------

    def _heuristic_analyze(self, context: MarketContext) -> RiskReport:
        """
        Pure feature-based risk assessment — no LLM required.

        Computes a risk_score in [0.0, 1.0] from five weighted components,
        derives volatility regime, max position size, stop-loss percentage,
        and liquidity score directly from ``MarketContext`` data.
        """
        features = context.features

        # ------------------------------------------------------------------
        # 1. Safe feature extraction
        # ------------------------------------------------------------------
        def _get(key: str, default: float = 0.0) -> float:
            val = features.get(key, default)
            if val is None or not isinstance(val, (int, float)):
                return default
            return float(val)

        rsi = _get("rsi_14", 50.0)
        adx = _get("adx_14", 25.0)
        volume = _get("volume", 0.0)
        volume_sma = _get("volume_sma", 0.0)

        # ------------------------------------------------------------------
        # 2. Volatility regime from ATR%
        # ------------------------------------------------------------------
        atr = context.atr
        price = context.current_price
        atr_pct = (atr / price * 100) if price > 0 else 0.0

        if atr_pct < 0.5:
            vol_regime = "LOW"
        elif atr_pct < 1.5:
            vol_regime = "MEDIUM"
        elif atr_pct < 3.0:
            vol_regime = "HIGH"
        else:
            vol_regime = "EXTREME"

        # ------------------------------------------------------------------
        # 3. Risk score (0.0–1.0) from five weighted components
        # ------------------------------------------------------------------
        risk_components: list[float] = []

        # a) Volatility risk (higher ATR% = higher risk) — 30% weight
        vol_risk = min(atr_pct / 4.0, 1.0)  # 4% ATR → full vol risk
        risk_components.append(vol_risk * 0.30)

        # b) RSI extreme risk — 15% weight
        #    Risk ramps up beyond ±20 from center (50): e.g. RSI 75 → risk 0.17
        rsi_risk = max(0.0, (abs(rsi - 50.0) - 20.0) / 30.0)
        rsi_risk = min(rsi_risk, 1.0)
        risk_components.append(rsi_risk * 0.15)

        # c) Position exposure risk — 25% weight
        #    10 open positions = max exposure risk
        pos_risk = min(context.open_positions / 10.0, 1.0)
        risk_components.append(pos_risk * 0.25)

        # d) ADX chop risk — 15% weight
        #    Very low ADX = choppy market = risky for directional trades
        adx_risk = max(0.0, (25.0 - adx) / 25.0)  # ADX < 25 → increasing risk
        risk_components.append(adx_risk * 0.15)

        # e) Equity exposure risk (simplified) — 15% weight
        if context.equity > 0:
            equity_risk = min(context.open_positions * 0.1, 1.0)
        else:
            equity_risk = 0.5  # no equity data → moderate risk
        risk_components.append(equity_risk * 0.15)

        risk_score = sum(risk_components)
        risk_score = max(0.0, min(1.0, risk_score))

        # ------------------------------------------------------------------
        # 4. Blocking decision
        # ------------------------------------------------------------------
        blocking = risk_score > self.RISK_BLOCK_THRESHOLD

        # ------------------------------------------------------------------
        # 5. Max position size (% of equity) — inversely proportional to risk
        # ------------------------------------------------------------------
        if blocking:
            max_size = 0.0
        else:
            max_size = max(0.5, 2.0 * (1.0 - risk_score))  # range: 0.5% to 2.0%

        # ------------------------------------------------------------------
        # 6. Recommended stop-loss as % of price (1.5× ATR%)
        # ------------------------------------------------------------------
        sl_pct = atr_pct * 1.5

        # ------------------------------------------------------------------
        # 7. Liquidity score from volume vs. volume_sma
        # ------------------------------------------------------------------
        if volume_sma > 0:
            # normalise to [0, 1]: 2× average volume = max score of 1.0
            liq_score = min(volume / volume_sma, 2.0) / 2.0
        else:
            liq_score = 0.5  # no volume data → neutral

        # ------------------------------------------------------------------
        # 8. Rationale summary
        # ------------------------------------------------------------------
        rationale = (
            f"Risk {risk_score:.2f}: vol={vol_regime}({atr_pct:.2f}%), "
            f"positions={context.open_positions}, ADX={adx:.1f}, RSI={rsi:.1f}"
        )

        return RiskReport(
            risk_score=round(risk_score, 4),
            volatility_regime=vol_regime,  # type: ignore[arg-type]
            max_position_size_pct=round(max_size, 2),
            recommended_stop_loss_pct=round(sl_pct, 4),
            liquidity_score=round(liq_score, 4),
            blocking=blocking,
            rationale=rationale,
        )
