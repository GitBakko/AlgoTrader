# MANTIS-EVOLUTION: Technical Analyst Agent
"""
TechnicalAnalystAgent — the technical analysis specialist in the MANTIS AI
multi-agent trading system.

Two analysis paths:
1. **LLM path** (default): calls Claude via base class ``_call_llm()`` for
   rich, narrative-quality reasoning about price action.
2. **Heuristic fallback**: pure computation from the feature dict, used when
   the LLM path fails (API outage, rate-limit, import error) or is disabled.

The heuristic path uses the same feature keys that the MANTIS feature pipeline
already produces (ema_9, ema_21, rsi_14, adx_14, macd_histogram, bb_upper,
bb_lower, vwap) — so it is always operational, with zero external dependencies.
"""

from __future__ import annotations

from loguru import logger

from src.agents.base_agent import MantisBaseAgent
from src.agents.schemas import AgentRole, MarketContext, TechnicalReport


class TechnicalAnalystAgent(MantisBaseAgent):
    """
    Technical analysis agent for MANTIS AI.

    Produces a ``TechnicalReport`` by either:
    - Calling Claude (LLM path) for nuanced price-action reasoning, or
    - Computing a heuristic report directly from the feature dict (fallback).
    """

    role = AgentRole.TECHNICAL
    output_schema = TechnicalReport

    # ------------------------------------------------------------------
    # Abstract interface implementation
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        """Return the role-specific system prompt for technical analysis."""
        return (
            "You are an expert technical analyst specialising in crypto and forex markets. "
            "You have deep knowledge of price action, trend analysis, momentum indicators, "
            "volatility measures, and key support/resistance levels.\n\n"
            "Your task is to analyse the provided market features and produce a structured "
            "technical analysis report. You must:\n"
            "1. Determine trend direction (BULLISH, BEARISH, or NEUTRAL) based on EMA alignment\n"
            "2. Score trend strength from 0.0 (no trend) to 1.0 (extremely strong trend)\n"
            "3. Identify key support and resistance levels from Bollinger Bands and VWAP\n"
            "4. List active chart patterns and indicator conditions\n"
            "5. Provide a concise rationale explaining your analysis\n\n"
            "Respond ONLY with valid JSON matching the requested schema. "
            "Do not include any explanation outside the JSON object."
        )

    def _build_user_message(self, context: MarketContext) -> str:
        """Format the MarketContext into a structured analysis prompt for Claude."""
        features = context.features
        lines = [
            f"## Technical Analysis Request: {context.epic}",
            f"",
            f"**Asset**: {context.epic}",
            f"**Timeframe**: {context.timeframe}",
            f"**Current Price**: {context.current_price:.6g}",
            f"**ATR**: {context.atr:.6g}",
            f"**Regime**: {context.regime or 'UNKNOWN'}",
            f"",
            f"### Feature Data",
        ]

        if features:
            # Group features for readability
            trend_indicators = {
                k: v for k, v in features.items()
                if any(k.startswith(p) for p in ("ema_", "sma_", "dema_", "tema_"))
            }
            momentum_indicators = {
                k: v for k, v in features.items()
                if any(k.startswith(p) for p in ("rsi", "macd", "stoch", "cci", "mfi"))
            }
            volatility_indicators = {
                k: v for k, v in features.items()
                if any(k.startswith(p) for p in ("bb_", "atr", "keltner", "adx"))
            }
            volume_indicators = {
                k: v for k, v in features.items()
                if any(k.startswith(p) for p in ("volume", "obv", "vwap"))
            }

            # Remaining features
            categorised_keys = (
                set(trend_indicators)
                | set(momentum_indicators)
                | set(volatility_indicators)
                | set(volume_indicators)
            )
            other_indicators = {k: v for k, v in features.items() if k not in categorised_keys}

            def _fmt_group(title: str, d: dict) -> list[str]:
                if not d:
                    return []
                out = [f"**{title}**:"]
                for k, v in d.items():
                    formatted_v = f"{v:.6g}" if isinstance(v, (int, float)) and v is not None else str(v)
                    out.append(f"  - {k}: {formatted_v}")
                return out

            lines += _fmt_group("Trend (EMA/SMA)", trend_indicators)
            lines += _fmt_group("Momentum (RSI/MACD/Stoch)", momentum_indicators)
            lines += _fmt_group("Volatility (BB/ATR/ADX)", volatility_indicators)
            lines += _fmt_group("Volume (OBV/VWAP)", volume_indicators)
            if other_indicators:
                lines += _fmt_group("Other Features", other_indicators)
        else:
            lines.append("  *(no feature data available)*")

        lines += [
            "",
            "### Task",
            f"Analyse {context.epic} at {context.current_price:.6g} and produce a TechnicalReport JSON.",
            "Focus on the EMA alignment for trend direction, RSI/MACD for momentum, "
            "ADX for trend strength, and BB levels for support/resistance.",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public entry point — LLM first, heuristic fallback
    # ------------------------------------------------------------------

    async def analyze(self, context: MarketContext) -> TechnicalReport | None:
        """
        Try the LLM path first; fall back to heuristic analysis on any failure.

        Unlike the base ``analyze()`` which returns ``None`` on failure, this
        subclass ALWAYS returns a ``TechnicalReport`` — the heuristic path
        guarantees a result even when Claude is unreachable.
        """
        result = await super().analyze(context)
        if result is not None:
            return result
        logger.info(
            f"[TECHNICAL] LLM path unavailable for {context.epic}, "
            "using heuristic fallback."
        )
        return self._heuristic_analyze(context)

    # ------------------------------------------------------------------
    # Heuristic analysis — zero external dependencies
    # ------------------------------------------------------------------

    def _heuristic_analyze(self, context: MarketContext) -> TechnicalReport:
        """
        Pure feature-based technical analysis — no LLM required.

        Computes trend direction, strength score, key levels, and active
        patterns directly from the ``context.features`` dict using the
        standard MANTIS feature keys.
        """
        features = context.features

        # --- safe feature extraction (handles missing / None gracefully) ---
        def _get(key: str, default: float = 0.0) -> float:
            val = features.get(key, default)
            if val is None or not isinstance(val, (int, float)):
                return default
            return float(val)

        ema_9 = _get("ema_9")
        ema_21 = _get("ema_21")
        rsi_14 = _get("rsi_14", 50.0)
        adx_14 = _get("adx_14", 0.0)
        macd_hist = _get("macd_histogram", 0.0)
        bb_upper = _get("bb_upper", 0.0)
        bb_lower = _get("bb_lower", 0.0)
        vwap = _get("vwap", 0.0)

        # ----------------------------------------------------------------
        # 1. Trend direction — based on EMA crossover
        #    Threshold: > 0.1% spread required to declare directional bias
        # ----------------------------------------------------------------
        trend_direction: str
        if ema_21 > 0 and ema_9 > 0:
            spread_pct = (ema_9 - ema_21) / ema_21 * 100.0
            if spread_pct > 0.1:
                trend_direction = "BULLISH"
            elif spread_pct < -0.1:
                trend_direction = "BEARISH"
            else:
                trend_direction = "NEUTRAL"
        else:
            trend_direction = "NEUTRAL"

        # ----------------------------------------------------------------
        # 2. Strength score (0.0–1.0) — average of four normalised signals
        # ----------------------------------------------------------------
        # EMA spread signal: abs spread % clamped to [0, 2], then / 2
        ema_spread_signal = 0.0
        if ema_21 > 0 and ema_9 > 0:
            abs_spread_pct = abs(ema_9 - ema_21) / ema_21 * 100.0
            ema_spread_signal = min(abs_spread_pct, 2.0) / 2.0

        # RSI signal: distance from neutral (50), normalised to [0, 1]
        rsi_signal = abs(rsi_14 - 50.0) / 50.0

        # ADX signal: clamped to [0, 1] at ADX = 50
        adx_signal = min(adx_14 / 50.0, 1.0)

        # MACD alignment: 1.0 if histogram aligns with declared trend, else 0.0
        if trend_direction == "BULLISH":
            macd_signal = 1.0 if macd_hist > 0 else 0.0
        elif trend_direction == "BEARISH":
            macd_signal = 1.0 if macd_hist < 0 else 0.0
        else:
            macd_signal = 0.0

        raw_score = (ema_spread_signal + rsi_signal + adx_signal + macd_signal) / 4.0
        strength_score = max(0.0, min(raw_score, 1.0))

        # ----------------------------------------------------------------
        # 3. Key levels — from Bollinger Bands and VWAP
        # ----------------------------------------------------------------
        key_support_levels: list[float] = []
        key_resistance_levels: list[float] = []

        if bb_lower > 0:
            key_support_levels.append(bb_lower)
        if vwap > 0:
            key_support_levels.append(vwap)
        if bb_upper > 0:
            key_resistance_levels.append(bb_upper)

        # ----------------------------------------------------------------
        # 4. Active patterns — indicator condition flags
        # ----------------------------------------------------------------
        active_patterns: list[str] = []

        # EMA crossover: both EMAs valid and within 0.5% of each other
        if ema_9 > 0 and ema_21 > 0:
            crossover_pct = abs(ema_9 - ema_21) / ema_21 * 100.0
            if crossover_pct <= 0.5:
                active_patterns.append("EMA_CROSSOVER")

        # RSI extremes
        if features.get("rsi_14") is not None and isinstance(features.get("rsi_14"), (int, float)):
            if rsi_14 < 30:
                active_patterns.append("RSI_OVERSOLD")
            elif rsi_14 > 70:
                active_patterns.append("RSI_OVERBOUGHT")

        # Strong trend
        if features.get("adx_14") is not None and isinstance(features.get("adx_14"), (int, float)):
            if adx_14 > 25:
                active_patterns.append("STRONG_TREND")

        # MACD direction
        if features.get("macd_histogram") is not None and isinstance(
            features.get("macd_histogram"), (int, float)
        ):
            if macd_hist > 0:
                active_patterns.append("MACD_BULLISH")
            elif macd_hist < 0:
                active_patterns.append("MACD_BEARISH")

        # ----------------------------------------------------------------
        # 5. Assemble report
        # ----------------------------------------------------------------
        trend_str = trend_direction  # e.g. "BULLISH"
        return TechnicalReport(
            symbol=context.epic,
            trend_direction=trend_direction,  # type: ignore[arg-type]
            strength_score=strength_score,
            key_support_levels=key_support_levels,
            key_resistance_levels=key_resistance_levels,
            active_patterns=active_patterns,
            timeframe_consensus={context.timeframe: trend_str},
            rationale=(
                f"Heuristic analysis based on EMA/RSI/MACD/ADX. "
                f"EMA spread: {(ema_9-ema_21)/ema_21*100:.3f}% "
                if ema_21 > 0 and ema_9 > 0
                else "Heuristic analysis based on EMA/RSI/MACD/ADX. "
            ) + (
                f"RSI: {rsi_14:.1f}, ADX: {adx_14:.1f}, "
                f"MACD hist: {macd_hist:.4f}."
            ),
        )
