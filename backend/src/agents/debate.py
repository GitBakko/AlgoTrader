# MANTIS-EVOLUTION: Bull/Bear Debate Module
"""
BullBearDebate — structured bull/bear argumentation for trade proposals.

Takes reports from analyst agents (technical, sentiment, risk) and a trade
proposal, then builds structured arguments for and against the trade.

Two evaluation paths:
1. **LLM path** (opt-in, use_llm=True): reserved for future Claude integration
   — currently raises NotImplementedError (stub).
2. **Heuristic path** (default): deterministic, zero-dependency rule engine
   that converts analyst report fields directly into scored DebateArguments.

The heuristic path is ALWAYS available and covers:
  - Technical: trend direction + strength, resistance proximity
  - Sentiment: composite score, dominant narrative
  - Risk: risk score (high/low), liquidity score
"""

from __future__ import annotations

from loguru import logger

from src.agents.schemas import (
    DebateArgument,
    DebateSummary,
    RiskReport,
    SentimentReport,
    TechnicalReport,
    TradeProposal,
)


class BullBearDebate:
    """
    Structured debate: builds bull and bear arguments from analyst reports.

    LLM mode: uses Claude for nuanced evaluation (optional, not yet implemented).
    Heuristic mode: builds arguments from report data directly — zero external
    dependencies, always operational.

    Parameters
    ----------
    use_llm:
        If True, attempt the LLM path first and fall through to heuristic on
        any exception.  Defaults to False (heuristic only).
    model:
        Optional model identifier (back-compat). Ignored — the active
        LLMProvider owns backend + model selection.
    """

    def __init__(
        self,
        use_llm: bool = False,
        model: str | None = None,
    ) -> None:
        self.use_llm = use_llm
        self.model = model

    # ------------------------------------------------------------------
    # Public async entry point
    # ------------------------------------------------------------------

    async def debate(
        self,
        proposal: TradeProposal,
        technical: TechnicalReport | None,
        sentiment: SentimentReport | None,
        risk: RiskReport | None,
    ) -> DebateSummary:
        """
        Run the structured debate and return a DebateSummary.

        Tries the LLM path when ``use_llm=True``; falls through to the
        heuristic path on any exception (or when LLM is disabled).
        """
        if self.use_llm:
            try:
                return await self._llm_debate(proposal, technical, sentiment, risk)
            except Exception as exc:
                logger.warning(f"[DEBATE] LLM path failed ({exc!r}), falling back to heuristic.")
        return self._heuristic_debate(proposal, technical, sentiment, risk)

    # ------------------------------------------------------------------
    # LLM path — stub (reserved for future Claude integration)
    # ------------------------------------------------------------------

    async def _llm_debate(
        self,
        proposal: TradeProposal,
        technical: TechnicalReport | None,
        sentiment: SentimentReport | None,
        risk: RiskReport | None,
    ) -> DebateSummary:
        """
        LLM-powered debate via Claude.

        Not yet implemented — raises NotImplementedError.
        Set ``use_llm=False`` (the default) to use the heuristic path.
        """
        raise NotImplementedError(
            "LLM debate path is not yet implemented. Use use_llm=False for the "
            "heuristic path which is always available."
        )

    # ------------------------------------------------------------------
    # Heuristic path — deterministic rule engine
    # ------------------------------------------------------------------

    def _heuristic_debate(
        self,
        proposal: TradeProposal,
        technical: TechnicalReport | None,
        sentiment: SentimentReport | None,
        risk: RiskReport | None,
    ) -> DebateSummary:
        """
        Build BULL/BEAR arguments from analyst report fields.

        Rules
        -----
        Technical:
          - BULLISH trend  → BULL argument with strength_score confidence
          - BEARISH trend  → BEAR argument with strength_score confidence
          - Close resistance on BUY entry (< 1 % above entry) → BEAR argument

        Sentiment:
          - composite_score >  0.2 → BULL argument
          - composite_score < -0.2 → BEAR argument

        Risk:
          - risk_score > 0.5  → BEAR argument (elevated risk)
          - liquidity_score < 0.3 → BEAR argument (slippage risk)
          - risk_score < 0.3  → BULL argument (calm environment)

        Consensus
        ---------
        - BULLISH  if bull_total > bear_total × 1.2
        - BEARISH  if bear_total > bull_total × 1.2
        - NEUTRAL  otherwise

        Consensus confidence = |bull_total − bear_total| / (bull_total + bear_total),
        clamped to [0, 1].  Zero when there are no arguments at all.
        """
        bull_args: list[DebateArgument] = []
        bear_args: list[DebateArgument] = []

        # ----------------------------------------------------------------
        # Technical arguments
        # ----------------------------------------------------------------
        if technical is not None:
            if technical.trend_direction == "BULLISH":
                evidence = (
                    [f"Active patterns: {', '.join(technical.active_patterns)}"]
                    if technical.active_patterns
                    else []
                )
                bull_args.append(
                    DebateArgument(
                        side="BULL",
                        argument=(
                            f"Technical trend is BULLISH with "
                            f"{technical.strength_score:.0%} strength"
                        ),
                        confidence=technical.strength_score,
                        evidence=evidence,
                    )
                )
            elif technical.trend_direction == "BEARISH":
                evidence = (
                    [f"Active patterns: {', '.join(technical.active_patterns)}"]
                    if technical.active_patterns
                    else []
                )
                bear_args.append(
                    DebateArgument(
                        side="BEAR",
                        argument=(
                            f"Technical trend is BEARISH with "
                            f"{technical.strength_score:.0%} strength"
                        ),
                        confidence=technical.strength_score,
                        evidence=evidence,
                    )
                )

            # Resistance proximity: only relevant for BUY proposals.
            # H5 fix: pick the nearest resistance ABOVE entry, not the
            # globally lowest. Otherwise resistances below entry (e.g.,
            # previous swing-low support that the LLM also added to the
            # resistance list) trigger a spurious BEAR with `min()` <
            # entry * 1.01 always True.
            if technical.key_resistance_levels and proposal.action == "BUY":
                resistances_above = [
                    r for r in technical.key_resistance_levels if r > proposal.entry_price
                ]
                if resistances_above:
                    nearest_resistance = min(resistances_above)
                    if nearest_resistance < proposal.entry_price * 1.01:
                        bear_args.append(
                            DebateArgument(
                                side="BEAR",
                                argument=(
                                    f"Resistance at {nearest_resistance:.2f} is very close "
                                    f"to entry ({proposal.entry_price:.2f})"
                                ),
                                confidence=0.6,
                                evidence=[],
                            )
                        )

        # ----------------------------------------------------------------
        # Sentiment arguments
        # ----------------------------------------------------------------
        if sentiment is not None:
            if sentiment.composite_score > 0.2:
                bull_args.append(
                    DebateArgument(
                        side="BULL",
                        argument=(
                            f"Sentiment is bullish " f"(composite={sentiment.composite_score:.2f})"
                        ),
                        confidence=sentiment.confidence,
                        evidence=[f"Narrative: {sentiment.dominant_narrative}"],
                    )
                )
            elif sentiment.composite_score < -0.2:
                bear_args.append(
                    DebateArgument(
                        side="BEAR",
                        argument=(
                            f"Sentiment is bearish " f"(composite={sentiment.composite_score:.2f})"
                        ),
                        confidence=sentiment.confidence,
                        evidence=[f"Narrative: {sentiment.dominant_narrative}"],
                    )
                )

        # ----------------------------------------------------------------
        # Risk arguments
        # ----------------------------------------------------------------
        if risk is not None:
            if risk.risk_score > 0.5:
                bear_args.append(
                    DebateArgument(
                        side="BEAR",
                        argument=(
                            f"Elevated risk: {risk.volatility_regime} volatility, "
                            f"score={risk.risk_score:.2f}"
                        ),
                        confidence=risk.risk_score,
                        evidence=[risk.rationale],
                    )
                )
            if risk.liquidity_score < 0.3:
                bear_args.append(
                    DebateArgument(
                        side="BEAR",
                        argument="Low liquidity — slippage risk",
                        confidence=0.5,
                        evidence=[],
                    )
                )
            if risk.risk_score < 0.3:
                bull_args.append(
                    DebateArgument(
                        side="BULL",
                        argument=(f"Low risk environment " f"(score={risk.risk_score:.2f})"),
                        confidence=1.0 - risk.risk_score,
                        evidence=[],
                    )
                )

        # ----------------------------------------------------------------
        # Determine consensus
        # ----------------------------------------------------------------
        bull_total = sum(a.confidence for a in bull_args) if bull_args else 0.0
        bear_total = sum(a.confidence for a in bear_args) if bear_args else 0.0

        if bull_total > bear_total * 1.2:
            consensus = "BULLISH"
        elif bear_total > bull_total * 1.2:
            consensus = "BEARISH"
        else:
            consensus = "NEUTRAL"

        total = bull_total + bear_total
        if total > 0.0:
            consensus_confidence = abs(bull_total - bear_total) / total
        else:
            consensus_confidence = 0.0
        consensus_confidence = max(0.0, min(1.0, round(consensus_confidence, 4)))

        # ----------------------------------------------------------------
        # Key disagreements — only when both sides have arguments
        # ----------------------------------------------------------------
        disagreements: list[str] = []
        if bull_args and bear_args:
            disagreements.append(
                f"Bull ({len(bull_args)} args, weight={bull_total:.2f}) vs "
                f"Bear ({len(bear_args)} args, weight={bear_total:.2f})"
            )

        return DebateSummary(
            bull_arguments=bull_args,
            bear_arguments=bear_args,
            consensus=consensus,  # type: ignore[arg-type]
            consensus_confidence=consensus_confidence,
            key_disagreements=disagreements,
        )
