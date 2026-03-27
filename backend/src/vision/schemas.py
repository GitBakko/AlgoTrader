# MANTIS-EVOLUTION: Vision AI schema contracts
"""
Pydantic schema contracts for the Vision AI subsystem.

Defines the data structures flowing through chart generation,
vision analysis, and the orchestrator integration layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChartConfig(BaseModel):
    """Configuration for chart generation."""

    width: int = 1200
    height: int = 600
    show_ema: bool = True
    show_bollinger: bool = True
    show_volume: bool = True
    show_rsi: bool = True
    style: str = "nightclouds"  # mplfinance style (informational — we use matplotlib)


class VisionReport(BaseModel):
    """Output of the Vision Analyzer."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trend_direction: Literal["BULLISH", "BEARISH", "NEUTRAL", "RANGING"] = "NEUTRAL"
    key_patterns: list[str] = Field(default_factory=list)
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    volume_analysis: str = ""
    momentum: Literal["BUILDING", "FADING", "NEUTRAL"] = "NEUTRAL"
    visual_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    actionable_insight: str = ""
    chart_hash: str = ""


class VisionSignal(BaseModel):
    """Output from the Vision Agent for the orchestrator."""

    vision_report: VisionReport | None = None
    rag_context_summary: str = ""
    chart_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
