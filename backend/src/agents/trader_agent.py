# MANTIS-EVOLUTION: Trader Agent
"""
TraderAgent — pure logic combining analyst reports into a TradeProposal.

This agent does NOT inherit from MantisBaseAgent.
No LLM, no API calls — deterministic weighted scoring only.
"""

from __future__ import annotations

from src.agents.schemas import (
    MarketContext,
    RiskReport,
    SentimentReport,
    TechnicalReport,
    TradeProposal,
)


class TraderAgent:
    """
    Combines analyst reports into a TradeProposal.
    Pure logic — no LLM, no API calls.

    Scoring:
    - direction_score  = weighted combination of technical + sentiment signals
    - confidence       = weighted average of individual report confidences
    - size_pct         = taken directly from RiskReport.max_position_size_pct
    - SL/TP            = derived from TechnicalReport key levels
    """

    def __init__(
        self,
        technical_weight: float = 0.4,
        sentiment_weight: float = 0.2,
        risk_weight: float = 0.4,
    ) -> None:
        self.technical_weight = technical_weight
        self.sentiment_weight = sentiment_weight
        self.risk_weight = risk_weight

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propose(
        self,
        technical: TechnicalReport | None,
        sentiment: SentimentReport | None,
        risk: RiskReport | None,
        context: MarketContext,
    ) -> TradeProposal:
        """Generate a trade proposal from analyst reports."""

        # 1. If risk blocks → HOLD immediately
        if risk and risk.blocking:
            return TradeProposal(
                action="HOLD",
                confidence=0.0,
                size_pct=0.0,
                entry_price=context.current_price,
                take_profit_levels=[],
                stop_loss=0.0,
                rationale=f"Risk veto: {risk.rationale}",
                source_reports=self._build_sources(technical, sentiment, risk),
            )

        # 2. Determine direction from technical + sentiment
        tech_direction = self._direction_score(technical)  # -1 (bearish) to +1 (bullish)
        sent_direction = self._sentiment_score(sentiment)  # -1 to +1

        combined_weight = self.technical_weight + self.sentiment_weight
        if combined_weight > 0:
            direction_score = (
                tech_direction * self.technical_weight + sent_direction * self.sentiment_weight
            ) / combined_weight
        else:
            direction_score = 0.0

        # Map to action
        if direction_score > 0.15:
            action = "BUY"
        elif direction_score < -0.15:
            action = "SELL"
        else:
            action = "HOLD"

        # 3. Confidence: weighted average of report confidences
        confidences: list[tuple[float, float]] = []
        if technical:
            confidences.append((technical.strength_score, self.technical_weight))
        if sentiment:
            confidences.append((sentiment.confidence, self.sentiment_weight))
        if risk:
            # Risk confidence is inversely proportional to risk_score
            risk_conf = 1.0 - risk.risk_score
            confidences.append((risk_conf, self.risk_weight))

        if confidences:
            total_weight = sum(w for _, w in confidences)
            confidence = (
                sum(c * w for c, w in confidences) / total_weight if total_weight > 0 else 0.5
            )
        else:
            confidence = 0.0

        confidence = max(0.0, min(1.0, confidence))

        # If action is HOLD, confidence collapses to 0
        if action == "HOLD":
            confidence = 0.0

        # 4. Size from risk report (default 1.0 when no risk provided)
        size_pct = risk.max_position_size_pct if risk else 1.0

        # 5. SL/TP from technical key levels
        entry_price = context.current_price
        if action == "BUY" and technical:
            stop_loss = (
                min(technical.key_support_levels)
                if technical.key_support_levels
                else entry_price * 0.98
            )
            tp_levels = [l for l in technical.key_resistance_levels if l > entry_price]
        elif action == "SELL" and technical:
            stop_loss = (
                max(technical.key_resistance_levels)
                if technical.key_resistance_levels
                else entry_price * 1.02
            )
            tp_levels = [l for l in technical.key_support_levels if l < entry_price]
        else:
            stop_loss = 0.0
            tp_levels = []

        rationale = self._build_rationale(action, technical, sentiment, risk, direction_score)

        return TradeProposal(
            action=action,
            confidence=round(confidence, 4),
            size_pct=round(size_pct, 2),
            entry_price=entry_price,
            take_profit_levels=tp_levels,
            stop_loss=stop_loss,
            rationale=rationale,
            source_reports=self._build_sources(technical, sentiment, risk),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _direction_score(self, technical: TechnicalReport | None) -> float:
        """Map trend_direction + strength_score to a signed score in [-1, 1]."""
        if not technical:
            return 0.0
        if technical.trend_direction == "BULLISH":
            return technical.strength_score
        if technical.trend_direction == "BEARISH":
            return -technical.strength_score
        return 0.0

    def _sentiment_score(self, sentiment: SentimentReport | None) -> float:
        """Return composite_score which is already in [-1, 1]."""
        if not sentiment:
            return 0.0
        return sentiment.composite_score

    def _build_sources(
        self,
        tech: TechnicalReport | None,
        sent: SentimentReport | None,
        risk: RiskReport | None,
    ) -> dict:
        sources: dict = {}
        if tech:
            sources["technical"] = tech.trend_direction
        if sent:
            sources["sentiment"] = f"composite={sent.composite_score:.2f}"
        if risk:
            sources["risk"] = f"score={risk.risk_score:.2f}, blocking={risk.blocking}"
        return sources

    def _build_rationale(
        self,
        action: str,
        tech: TechnicalReport | None,
        sent: SentimentReport | None,
        risk: RiskReport | None,
        dir_score: float,
    ) -> str:
        parts = [f"Action={action} (dir_score={dir_score:.2f})"]
        if tech:
            parts.append(f"Technical: {tech.trend_direction} ({tech.strength_score:.2f})")
        if sent:
            parts.append(f"Sentiment: {sent.composite_score:.2f}")
        if risk:
            parts.append(f"Risk: {risk.risk_score:.2f}")
        return " | ".join(parts)
