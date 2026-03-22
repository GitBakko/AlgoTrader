# MANTIS-EVOLUTION: Sentiment Analyst Agent
"""
SentimentAnalystAgent — the sentiment analysis specialist in the MANTIS AI
multi-agent trading system.

Two analysis paths:
1. **LLM path** (default): calls Claude via base class ``_call_llm()`` for
   narrative-quality reasoning about market sentiment.
2. **Heuristic fallback**: pure aggregation of SIL (Signal Intelligence Layer)
   data already present in ``MarketContext.sil_data``.  Used when the LLM path
   fails (API outage, rate-limit, import error) or is disabled.

The heuristic path aggregates four SIL sources:
  - ``sil_fear_greed_value``      — Fear & Greed index, raw range [0, 1]
  - ``sil_alpha_sentiment_score`` — Alpha-sentiment score, range [-1, 1]
  - ``sil_social_bullish_ratio``  — Social bullish ratio, range [0, 1]
  - ``sil_cot_net_position_norm`` — COT net-position normalised, range [-1, 1]

All normalised to [-1, 1] before weighting, so the final composite is also
in [-1, 1].  This path is always operational, with zero external dependencies.
"""

from __future__ import annotations

from loguru import logger

from src.agents.base_agent import MantisBaseAgent
from src.agents.schemas import AgentRole, MarketContext, SentimentReport


class SentimentAnalystAgent(MantisBaseAgent):
    """
    Sentiment analysis agent for MANTIS AI.

    Produces a ``SentimentReport`` by either:
    - Calling Claude (LLM path) for nuanced sentiment reasoning, or
    - Aggregating SIL data directly from ``MarketContext.sil_data`` (fallback).
    """

    role = AgentRole.SENTIMENT
    output_schema = SentimentReport

    # ------------------------------------------------------------------
    # Abstract interface implementation
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        """Return the role-specific system prompt for sentiment analysis."""
        return (
            "You are an expert market sentiment analyst specialising in crypto, forex, "
            "and commodity markets.  You have deep knowledge of Fear & Greed indices, "
            "COT positioning data, social media sentiment, and macroeconomic news flows.\n\n"
            "Your task is to analyse the provided SIL (Signal Intelligence Layer) data and "
            "produce a structured sentiment report.  You must:\n"
            "1. Compute a composite sentiment score in [-1.0, 1.0] "
            "(-1 = extreme fear/bearish, +1 = extreme greed/bullish)\n"
            "2. Rate your confidence in the analysis from 0.0 (no data) to 1.0 (strong consensus)\n"
            "3. Identify the dominant narrative in one sentence\n"
            "4. Echo back the raw Fear & Greed index, social bullish ratio, and news sentiment\n\n"
            "Respond ONLY with valid JSON matching the requested schema. "
            "Do not include any explanation outside the JSON object."
        )

    def _build_user_message(self, context: MarketContext) -> str:
        """Format the MarketContext into a structured sentiment analysis prompt for Claude."""
        sil = context.sil_data or {}
        lines = [
            f"## Sentiment Analysis Request: {context.epic}",
            "",
            f"**Asset**: {context.epic}",
            f"**Timeframe**: {context.timeframe}",
            f"**Current Price**: {context.current_price:.6g}",
            f"**ATR**: {context.atr:.6g}",
            "",
            "### SIL (Signal Intelligence Layer) Data",
        ]

        if sil:
            for key, value in sil.items():
                formatted_v = (
                    f"{value:.6g}" if isinstance(value, (int, float)) and value is not None
                    else str(value)
                )
                lines.append(f"  - {key}: {formatted_v}")
        else:
            lines.append("  *(no SIL data available — use defaults)*")

        lines += [
            "",
            "### Task",
            f"Analyse the sentiment for {context.epic} at {context.current_price:.6g} "
            "and produce a SentimentReport JSON.",
            "Weight Fear & Greed at 30%, alpha/news sentiment at 25%, COT at 25%, "
            "and social sentiment at 20%.",
            "Normalise Fear & Greed and social bullish ratio from [0, 1] to [-1, 1] "
            "before computing the composite.",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public entry point — LLM first, heuristic fallback
    # ------------------------------------------------------------------

    async def analyze(self, context: MarketContext) -> SentimentReport | None:
        """
        Try the LLM path first; fall back to heuristic analysis on any failure.

        Unlike the base ``analyze()`` which returns ``None`` on failure, this
        subclass ALWAYS returns a ``SentimentReport`` — the heuristic path
        guarantees a result even when Claude is unreachable or the SIL data
        is sparse.
        """
        result = await super().analyze(context)
        if result is not None:
            return result
        logger.info(
            f"[SENTIMENT] LLM path unavailable for {context.epic}, "
            "using heuristic fallback."
        )
        return self._heuristic_analyze(context)

    # ------------------------------------------------------------------
    # Heuristic analysis — zero external dependencies
    # ------------------------------------------------------------------

    def _heuristic_analyze(self, context: MarketContext) -> SentimentReport:
        """
        Pure SIL data aggregation — no LLM required.

        Aggregates four sentiment sources from ``context.sil_data`` using a
        fixed weighting scheme, normalises Fear & Greed and social ratio to
        [-1, 1], then computes confidence from source-direction agreement.
        """
        sil = context.sil_data or {}

        # ------------------------------------------------------------------
        # 1. Extract raw SIL values with safe defaults
        # ------------------------------------------------------------------
        # fear_greed: raw [0, 1] — 0.5 = neutral
        fear_greed: float = float(sil.get("sil_fear_greed_value", 0.5))
        # alpha sentiment: already in [-1, 1]
        alpha_sentiment: float = float(sil.get("sil_alpha_sentiment_score", 0.0))
        # social bullish ratio: raw [0, 1] — 0.5 = neutral
        social_bullish: float = float(sil.get("sil_social_bullish_ratio", 0.5))
        # COT net position: already in [-1, 1]
        cot_net: float = float(sil.get("sil_cot_net_position_norm", 0.0))

        # ------------------------------------------------------------------
        # 2. Normalise [0, 1] sources to [-1, 1]
        # ------------------------------------------------------------------
        fg_normalized: float = (fear_greed - 0.5) * 2.0
        social_normalized: float = (social_bullish - 0.5) * 2.0

        # ------------------------------------------------------------------
        # 3. Composite score: weighted average of all four normalised sources
        #    Weights: Fear & Greed 30%, Alpha 25%, COT 25%, Social 20%
        # ------------------------------------------------------------------
        composite = (
            fg_normalized * 0.30
            + alpha_sentiment * 0.25
            + cot_net * 0.25
            + social_normalized * 0.20
        )
        composite = max(-1.0, min(1.0, composite))  # clamp to [-1, 1]

        # ------------------------------------------------------------------
        # 4. Confidence: based on source-direction agreement
        #    High agreement → high confidence; split signals → low confidence
        # ------------------------------------------------------------------
        sources = [fg_normalized, alpha_sentiment, cot_net, social_normalized]
        non_zero = [s for s in sources if abs(s) > 0.05]

        if not non_zero:
            # No meaningful signal in any source → minimal confidence
            confidence: float = 0.1
        else:
            signs = [1 if s > 0 else -1 for s in non_zero]
            # agreement: 1.0 = all same direction, 0.0 = perfectly split
            agreement = abs(sum(signs)) / len(signs)
            # scale to [0.2, 1.0]: even a single source gives base confidence 0.2
            confidence = max(0.1, min(1.0, agreement * 0.8 + 0.2))

        # ------------------------------------------------------------------
        # 5. Dominant narrative
        # ------------------------------------------------------------------
        if composite > 0.2:
            narrative = "Predominantly bullish sentiment across sources"
        elif composite < -0.2:
            narrative = "Predominantly bearish sentiment across sources"
        else:
            narrative = "Mixed or neutral sentiment"

        return SentimentReport(
            composite_score=round(composite, 4),
            fear_greed_index=fear_greed,
            social_sentiment=social_bullish,
            news_sentiment=alpha_sentiment,
            confidence=round(confidence, 4),
            dominant_narrative=narrative,
        )
