# MANTIS AI Evolution: Multi-Agent + RL + Memory + Vision + DRL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform MANTIS from a single-model XGBoost system into a multi-agent, memory-aware, RL-enhanced trading platform with vision AI and DRL ensemble capabilities.

**Architecture:** Five new packages (`agents/`, `rl/`, `memory_layer/`, `vision/`, `drl/`) under `backend/src/`. Each package is self-contained with clear interfaces. The `MantisAgentOrchestrator` is the central coordinator — it wraps the existing `generate_signal()` flow, adding LLM-based agents, RL signals, memory context, and DRL ensemble voting. The existing XGBoost pipeline remains untouched and becomes one input among many.

**Tech Stack:** Python 3.12+, FastAPI, Anthropic SDK (Claude API), stable-baselines3, gymnasium, sentence-transformers, faiss-cpu, mplfinance, Pydantic v2, Polars, numpy

**Branch:** `feature/evolution-multi-agent`

---

## File Structure

### New Files (Sprint 1: Multi-Agent)
```
backend/src/agents/
├── __init__.py              # Package exports
├── schemas.py               # All agent Pydantic models (shared contracts)
├── base_agent.py            # MantisBaseAgent ABC + Claude LLM wrapper
├── technical_analyst.py     # Consumes existing 220+ features
├── sentiment_analyst.py     # Aggregates SIL sentiment feeds
├── risk_manager_agent.py    # LLM-powered risk assessment (wraps existing risk stack)
├── trader_agent.py          # Combines reports into TradeProposal
├── debate.py                # Bull/Bear structured debate
├── fund_manager.py          # FundManager — final approval/rejection logic
└── orchestrator.py          # MantisAgentOrchestrator — coordinates all agents
```

### New Files (Sprint 2: RL)
```
backend/src/rl/
├── __init__.py
├── schemas.py               # RL-specific Pydantic models + config
├── environment.py           # MantisRLEnvironment (gymnasium.Env)
├── reward_functions.py      # 3 reward fns + composite
├── adaptive_trainer.py      # Background retraining thread
├── rl_agent.py              # MantisRLAgent (wraps into agent system)
└── feature_pipeline.py      # RL-specific feature normalization
```

### New Files (Sprint 3: Memory)
```
backend/src/memory_layer/
├── __init__.py
├── schemas.py               # Memory Pydantic models
├── short_term.py            # Circular buffer with exponential decay
├── long_term.py             # Pattern store with SQLite persistence
├── episodic.py              # High-impact episode store
├── memory_store.py          # Unified coordinator
├── embeddings.py            # Lightweight embeddings (MiniLM or TF-IDF fallback)
└── schema.sql               # SQLite schema for LTM + episodic
```

### New Files (Sprint 4: Vision + RAG)
```
backend/src/vision/
├── __init__.py
├── schemas.py               # Vision Pydantic models
├── chart_generator.py       # mplfinance chart generation
├── vision_analyzer.py       # Claude Vision API integration
└── vision_agent.py          # MantisVisionAgent for orchestrator

backend/src/rag/
├── __init__.py
├── schemas.py               # RAG Pydantic models
├── news_ingester.py         # Aggregates existing SIL news feeds
├── context_builder.py       # Builds RAG context string for agents
└── vector_store.py          # FAISS-based semantic search
```

### New Files (Sprint 5: DRL Ensemble)
```
backend/src/drl/
├── __init__.py
├── schemas.py               # DRL Pydantic models + config
├── base_drl_agent.py        # MantisDRLAgent ABC
├── agents/
│   ├── __init__.py
│   ├── ppo_agent.py         # PPO wrapper
│   ├── sac_agent.py         # SAC wrapper
│   ├── a2c_agent.py         # A2C wrapper
│   └── td3_agent.py         # TD3 wrapper
├── ensemble.py              # MantisDRLEnsemble (voting/routing)
├── trainer.py               # Train-test-compare pipeline
├── performance_analyzer.py  # Sharpe, Sortino, Calmar, etc.
├── drl_ensemble_agent.py    # Wraps ensemble for orchestrator
└── backtest.py              # DRL backtesting
```

### New Test Files
```
backend/tests/agents/
├── test_schemas.py
├── test_base_agent.py
├── test_technical_analyst.py
├── test_sentiment_analyst.py
├── test_risk_manager_agent.py
├── test_trader_agent.py
├── test_debate.py
└── test_orchestrator.py

backend/tests/rl/
├── test_environment.py
├── test_reward_functions.py
├── test_adaptive_trainer.py
├── test_rl_agent.py
└── test_feature_pipeline.py

backend/tests/memory_layer/
├── test_short_term.py
├── test_long_term.py
├── test_episodic.py
├── test_memory_store.py
└── test_embeddings.py

backend/tests/vision/
├── test_chart_generator.py
├── test_vision_analyzer.py
└── test_vision_agent.py

backend/tests/rag/
├── test_news_ingester.py
├── test_context_builder.py
└── test_vector_store.py

backend/tests/drl/
├── test_base_drl_agent.py
├── test_ppo_agent.py
├── test_ensemble.py
├── test_trainer.py
├── test_performance_analyzer.py
└── test_backtest.py
```

### Modified Files
```
backend/src/utils/config.py           # Add agents/rl/memory/vision/drl config sections
backend/src/trading/paper_loop.py     # Wire orchestrator as optional enhancement
backend/src/api/main.py               # Register new routers
backend/.env.example                  # Add ANTHROPIC_API_KEY + new env vars
backend/requirements_evolution.txt    # New dependencies
docs/MIGRATION_NOTE.md                # Breaking changes documented
```

---

## Sprint 1: Multi-Agent Architecture

### Task 1.1: Agent Schemas

**Files:**
- Create: `backend/src/agents/schemas.py`
- Test: `backend/tests/agents/test_schemas.py`

- [ ] **Step 1: Write test for all agent schemas**

```python
# tests/agents/test_schemas.py
"""Tests for agent Pydantic schemas — validate serialization, constraints, defaults."""
import pytest
from datetime import datetime, timezone
from src.agents.schemas import (
    AgentRole, MarketContext, TechnicalReport, SentimentReport,
    RiskReport, TradeProposal, FinalDecision, DebateSummary,
    DebateArgument,
)

class TestAgentRole:
    def test_all_roles_defined(self):
        roles = [r.value for r in AgentRole]
        assert "TECHNICAL" in roles
        assert "SENTIMENT" in roles
        assert "RISK" in roles
        assert "TRADER" in roles
        assert "FUND_MANAGER" in roles

class TestMarketContext:
    def test_create_minimal(self):
        ctx = MarketContext(
            epic="XAUUSD", timeframe="15min",
            current_price=2050.5, atr=15.3,
            features={"ema_9": 2049.0, "rsi_14": 62.5},
        )
        assert ctx.epic == "XAUUSD"
        assert ctx.regime is None  # optional

    def test_full_context(self):
        ctx = MarketContext(
            epic="BTCUSD", timeframe="15min",
            current_price=65000.0, atr=500.0,
            features={"ema_9": 64800.0},
            regime="trending_up",
            sil_data={"fear_greed": 72, "cot_net": 0.3},
            open_positions=2, equity=50000.0,
        )
        assert ctx.regime == "trending_up"
        assert ctx.open_positions == 2

class TestTechnicalReport:
    def test_valid_report(self):
        r = TechnicalReport(
            symbol="XAUUSD",
            trend_direction="BULLISH",
            strength_score=0.85,
            key_support_levels=[2040.0, 2020.0],
            key_resistance_levels=[2060.0, 2080.0],
            active_patterns=["EMA_CROSSOVER", "MACD_BULLISH"],
            timeframe_consensus={"15m": "BULLISH", "1h": "NEUTRAL"},
            rationale="Strong EMA crossover with MACD confirmation",
        )
        assert 0.0 <= r.strength_score <= 1.0

    def test_strength_score_clamped(self):
        with pytest.raises(Exception):  # ValidationError
            TechnicalReport(
                symbol="X", trend_direction="BULLISH", strength_score=1.5,
                key_support_levels=[], key_resistance_levels=[],
                active_patterns=[], timeframe_consensus={}, rationale="x",
            )

class TestRiskReport:
    def test_blocking_when_high_risk(self):
        r = RiskReport(
            risk_score=0.9,
            volatility_regime="EXTREME",
            max_position_size_pct=0.0,
            recommended_stop_loss_pct=0.05,
            liquidity_score=0.2,
            blocking=True,
            rationale="Extreme volatility detected",
        )
        assert r.blocking is True

    def test_not_blocking_normal(self):
        r = RiskReport(
            risk_score=0.3, volatility_regime="LOW",
            max_position_size_pct=2.0, recommended_stop_loss_pct=0.02,
            liquidity_score=0.8, blocking=False, rationale="Normal conditions",
        )
        assert r.blocking is False

class TestFinalDecision:
    def test_approved_decision(self):
        d = FinalDecision(
            action="BUY", confidence=0.75, size_pct=1.5,
            entry_price=2050.0, take_profit_levels=[2065.0, 2080.0],
            stop_loss=2035.0, rationale="Consensus bullish",
            source_reports={"technical": "bullish", "sentiment": "bullish"},
            approved=True, agent_audit_trail=[{"agent": "technical", "action": "BUY"}],
        )
        assert d.approved is True
        assert len(d.agent_audit_trail) > 0

    def test_rejected_decision(self):
        d = FinalDecision(
            action="HOLD", confidence=0.2, size_pct=0.0,
            entry_price=2050.0, take_profit_levels=[], stop_loss=0.0,
            rationale="Risk too high",
            source_reports={},
            approved=False,
            override_reason="Risk score > 0.8",
            agent_audit_trail=[],
        )
        assert d.approved is False
        assert d.override_reason is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents'`

- [ ] **Step 3: Implement schemas**

```python
# src/agents/schemas.py
# MANTIS-EVOLUTION: Agent schema contracts
"""Pydantic models for the multi-agent system. All agent communication uses these schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class AgentRole(str, Enum):
    TECHNICAL = "TECHNICAL"
    SENTIMENT = "SENTIMENT"
    RISK = "RISK"
    TRADER = "TRADER"
    FUND_MANAGER = "FUND_MANAGER"
    VISION = "VISION"
    RL_ADAPTIVE = "RL_ADAPTIVE"
    DRL_ENSEMBLE = "DRL_ENSEMBLE"


class MarketContext(BaseModel):
    """Shared market context passed to all agents."""
    epic: str
    timeframe: str = "15min"
    current_price: float
    atr: float
    features: dict[str, Any] = Field(default_factory=dict)
    regime: str | None = None
    sil_data: dict[str, Any] | None = None
    open_positions: int = 0
    equity: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TechnicalReport(BaseModel):
    """Output of the TechnicalAnalystAgent."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str
    trend_direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    strength_score: float = Field(ge=0.0, le=1.0)
    key_support_levels: list[float] = Field(default_factory=list)
    key_resistance_levels: list[float] = Field(default_factory=list)
    active_patterns: list[str] = Field(default_factory=list)
    timeframe_consensus: dict[str, str] = Field(default_factory=dict)
    rationale: str = ""


class SentimentReport(BaseModel):
    """Output of the SentimentAnalystAgent."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    composite_score: float = Field(ge=-1.0, le=1.0)
    fear_greed_index: float = 0.0
    social_sentiment: float = 0.0
    news_sentiment: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    dominant_narrative: str = ""


class RiskReport(BaseModel):
    """Output of the RiskManagerAgent."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risk_score: float = Field(ge=0.0, le=1.0)
    volatility_regime: Literal["LOW", "MEDIUM", "HIGH", "EXTREME"]
    max_position_size_pct: float = Field(ge=0.0)
    recommended_stop_loss_pct: float = Field(ge=0.0)
    liquidity_score: float = Field(ge=0.0, le=1.0, default=0.5)
    blocking: bool = False
    rationale: str = ""


class TradeProposal(BaseModel):
    """Output of the TraderAgent — a proposal, not a final decision."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    size_pct: float = Field(ge=0.0)
    entry_price: float = 0.0
    take_profit_levels: list[float] = Field(default_factory=list)
    stop_loss: float = 0.0
    rationale: str = ""
    source_reports: dict[str, Any] = Field(default_factory=dict)


class DebateArgument(BaseModel):
    """A single argument in the bull/bear debate."""
    side: Literal["BULL", "BEAR"]
    argument: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class DebateSummary(BaseModel):
    """Summary of the bull/bear debate."""
    bull_arguments: list[DebateArgument] = Field(default_factory=list)
    bear_arguments: list[DebateArgument] = Field(default_factory=list)
    consensus: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    consensus_confidence: float = Field(ge=0.0, le=1.0)
    key_disagreements: list[str] = Field(default_factory=list)


class FinalDecision(TradeProposal):
    """Output of the FundManager / Orchestrator — the final verdict."""
    approved: bool = False
    override_reason: str | None = None
    debate_summary: str | None = None
    agent_audit_trail: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Create `__init__.py` and run tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_schemas.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/__init__.py backend/src/agents/schemas.py backend/tests/agents/
git commit -m "feat(agents): add agent Pydantic schemas and contracts"
```

---

### Task 1.2: Base Agent Class

**Files:**
- Create: `backend/src/agents/base_agent.py`
- Test: `backend/tests/agents/test_base_agent.py`

- [ ] **Step 1: Write test for base agent**

```python
# tests/agents/test_base_agent.py
"""Tests for MantisBaseAgent — LLM wrapper with structured output."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.base_agent import MantisBaseAgent
from src.agents.schemas import AgentRole, MarketContext, TechnicalReport


class MockAgent(MantisBaseAgent):
    """Concrete test agent."""
    role = AgentRole.TECHNICAL
    output_schema = TechnicalReport

    def get_system_prompt(self) -> str:
        return "You are a test agent."

    def _build_user_message(self, context: MarketContext) -> str:
        return f"Analyze {context.epic} at {context.current_price}"


class TestMantisBaseAgent:
    def test_init_defaults(self):
        agent = MockAgent()
        assert agent.role == AgentRole.TECHNICAL
        assert agent.model == "claude-sonnet-4-20250514"

    def test_init_custom_model(self):
        agent = MockAgent(model="claude-haiku-4-5-20251001")
        assert agent.model == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_analyze_calls_llm_and_parses(self):
        agent = MockAgent()
        ctx = MarketContext(epic="XAUUSD", current_price=2050.0, atr=15.0)

        mock_response = TechnicalReport(
            symbol="XAUUSD", trend_direction="BULLISH",
            strength_score=0.8, rationale="Test",
        )
        with patch.object(agent, '_call_llm', new_callable=AsyncMock,
                          return_value=mock_response):
            result = await agent.analyze(ctx)
            assert isinstance(result, TechnicalReport)
            assert result.trend_direction == "BULLISH"

    @pytest.mark.asyncio
    async def test_analyze_returns_none_on_llm_failure(self):
        agent = MockAgent()
        ctx = MarketContext(epic="XAUUSD", current_price=2050.0, atr=15.0)

        with patch.object(agent, '_call_llm', new_callable=AsyncMock,
                          side_effect=Exception("API error")):
            result = await agent.analyze(ctx)
            assert result is None

    def test_token_budget_default(self):
        agent = MockAgent()
        assert agent.max_tokens >= 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_base_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement base agent**

```python
# src/agents/base_agent.py
# MANTIS-EVOLUTION: Agent base class
"""
Base agent class for MANTIS multi-agent system.
Every agent produces a Pydantic StructuredReport via Claude LLM reasoning.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from loguru import logger
from pydantic import BaseModel

from src.agents.schemas import AgentRole, MarketContext

T = TypeVar("T", bound=BaseModel)


class MantisBaseAgent(ABC):
    """
    Abstract base agent. Subclasses define:
    - role: AgentRole enum
    - output_schema: Pydantic model class for structured output
    - get_system_prompt(): role-specific system prompt
    - _build_user_message(): format MarketContext into user message
    """

    role: AgentRole
    output_schema: type[BaseModel]

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None  # lazy-init anthropic client

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent's role."""
        ...

    @abstractmethod
    def _build_user_message(self, context: MarketContext) -> str:
        """Format market context into the user message for the LLM."""
        ...

    async def analyze(self, context: MarketContext) -> BaseModel | None:
        """
        Run the agent's analysis pipeline:
        1. Build prompt from context
        2. Call Claude LLM
        3. Parse structured output
        Returns None on failure (never crashes the pipeline).
        """
        try:
            result = await self._call_llm(context)
            return result
        except Exception as e:
            logger.warning(f"[{self.role.value}] Agent analysis failed: {e!r}")
            return None

    async def _call_llm(self, context: MarketContext) -> BaseModel:
        """Call Claude API and parse response into output_schema."""
        client = self._get_client()
        system_prompt = self.get_system_prompt()
        user_message = self._build_user_message(context)

        # Request JSON output matching the schema
        schema_hint = json.dumps(
            self.output_schema.model_json_schema(), indent=2
        )
        full_system = (
            f"{system_prompt}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n"
            f"```json\n{schema_hint}\n```"
        )

        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=full_system,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract text content and parse as JSON
        text = response.content[0].text
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
        return self.output_schema.model_validate(data)

    def _get_client(self):
        """Lazy-initialize the Anthropic async client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic()
            except ImportError:
                raise RuntimeError(
                    "anthropic package required. "
                    "Install: pip install anthropic"
                )
        return self._client
```

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/agents/test_base_agent.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/base_agent.py backend/tests/agents/test_base_agent.py
git commit -m "feat(agents): add MantisBaseAgent with Claude LLM integration"
```

---

### Task 1.3: Technical Analyst Agent

**Files:**
- Create: `backend/src/agents/technical_analyst.py`
- Test: `backend/tests/agents/test_technical_analyst.py`

- [ ] **Step 1: Write test**

Test that the agent:
- Produces a TechnicalReport from MarketContext with features
- Correctly identifies trend from EMA/RSI/MACD features (without LLM — uses heuristic fallback)
- Has a proper system prompt mentioning technical analysis
- Handles missing features gracefully

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement TechnicalAnalystAgent**

Key design:
- Has a `_heuristic_analyze()` method that works WITHOUT LLM (pure feature-based)
- `analyze()` tries LLM first, falls back to heuristic on failure
- Consumes existing features from MarketContext.features dict (ema_9, ema_21, rsi_14, macd_histogram, adx_14, bb_upper, bb_lower, etc.)
- System prompt is specialized for technical analysis of crypto/forex

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add TechnicalAnalystAgent with heuristic fallback"
```

---

### Task 1.4: Sentiment Analyst Agent

**Files:**
- Create: `backend/src/agents/sentiment_analyst.py`
- Test: `backend/tests/agents/test_sentiment_analyst.py`

- [ ] **Step 1: Write test**

Test that:
- Produces SentimentReport from MarketContext.sil_data
- Normalizes Fear&Greed (0-100) to [-1, +1]
- Computes confidence from source consistency (all agree = high, mixed = low)
- Handles missing SIL data (returns neutral report)

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement SentimentAnalystAgent**

Key design:
- `_heuristic_analyze()` aggregates SIL data directly (no LLM needed for numbers)
- LLM used only for `dominant_narrative` generation
- Sources: sil_fear_greed_value, sil_alpha_sentiment_score, sil_social_bullish_ratio, sil_cot_net_position_norm
- Decay: more recent SIL data weighted higher

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add SentimentAnalystAgent with SIL data aggregation"
```

---

### Task 1.5: Risk Manager Agent

**Files:**
- Create: `backend/src/agents/risk_manager_agent.py`
- Test: `backend/tests/agents/test_risk_manager_agent.py`

- [ ] **Step 1: Write test**

Test that:
- Produces RiskReport with risk_score
- Sets blocking=True when risk_score > 0.8
- Uses ATR for volatility regime classification (LOW/MEDIUM/HIGH/EXTREME)
- Uses VPIN (or volume proxy) for liquidity_score
- Integrates with existing Kelly sizing parameters

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement RiskManagerAgent**

Key design:
- `_heuristic_analyze()` computes risk_score from: ATR ratio, RSI extremes, open positions count, equity drawdown
- Volatility regime: ATR < median = LOW, < 75th = MEDIUM, < 95th = HIGH, else EXTREME
- max_position_size_pct: driven by Kelly half-kelly or fixed-fractional
- Hard block at risk_score > 0.8

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add RiskManagerAgent with veto power at risk>0.8"
```

---

### Task 1.6: Trader Agent

**Files:**
- Create: `backend/src/agents/trader_agent.py`
- Test: `backend/tests/agents/test_trader_agent.py`

- [ ] **Step 1: Write test**

Test that:
- Combines TechnicalReport + SentimentReport + RiskReport → TradeProposal
- Returns HOLD if RiskReport.blocking is True
- Confidence is weighted average of input reports
- Includes SL/TP levels from RiskReport + TechnicalReport key levels

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement TraderAgent**

Key design:
- Does NOT inherit from MantisBaseAgent (does not need LLM)
- Pure logic: weighted merge of reports
- Weights configurable: technical=0.4, sentiment=0.2, risk=0.4
- If risk blocks → HOLD regardless
- SL from RiskReport.recommended_stop_loss_pct applied to entry_price
- TP levels from TechnicalReport.key_resistance_levels (for BUY) or key_support_levels (for SELL)

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add TraderAgent combining analyst reports"
```

---

### Task 1.7: Bull/Bear Debate

**Files:**
- Create: `backend/src/agents/debate.py`
- Test: `backend/tests/agents/test_debate.py`

- [ ] **Step 1: Write test**

Test that:
- Produces DebateSummary with bull and bear arguments
- Consensus reflects majority side
- Works without LLM (heuristic mode from reports)
- Handles edge case: all neutral → NEUTRAL consensus

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement BullBearDebate**

Key design:
- `_heuristic_debate()`: builds arguments from TechnicalReport + SentimentReport data
  - Bull arguments: positive indicators (EMA cross, RSI rising, positive sentiment)
  - Bear arguments: negative indicators (resistance near, RSI overbought, negative sentiment)
- `_llm_debate()`: sends both sides to Claude for structured evaluation (optional)
- temperature=0.2 for reproducibility

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add BullBearDebate with structured argumentation"
```

---

### Task 1.8: Fund Manager Agent

**Files:**
- Create: `backend/src/agents/fund_manager.py`
- Test: `backend/tests/agents/test_fund_manager.py`

- [ ] **Step 1: Write test**

Test that:
- FundManager receives TradeProposal + DebateSummary → FinalDecision
- Approves when debate consensus aligns with proposal and risk is acceptable
- Rejects when debate consensus opposes proposal
- Sets override_reason when rejecting
- Always populates agent_audit_trail

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement FundManagerAgent**

Key design:
- Receives: TradeProposal, DebateSummary, RiskReport
- Logic: If debate consensus OPPOSES proposal → reject (override_reason)
- If risk.blocking → reject
- If debate confidence < 0.3 → reject (too uncertain)
- Otherwise → approve with confidence = avg(proposal.confidence, debate.consensus_confidence)
- LLM mode: optionally uses Claude for nuanced evaluation (gated by config)

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add FundManagerAgent for final trade approval"
```

---

### Task 1.9: Agent Orchestrator (includes FundManager call)

**Files:**
- Create: `backend/src/agents/orchestrator.py`
- Test: `backend/tests/agents/test_orchestrator.py`

- [ ] **Step 1: Write test**

Test that:
- `run()` produces FinalDecision from MarketContext
- Pipeline executes in correct order: Technical → Sentiment → Risk → Trader → Debate → Decision
- Risk veto (blocking=True) → FinalDecision.approved=False
- agent_audit_trail is always populated
- Handles individual agent failures gracefully (logs warning, continues)
- Legacy wrapper `generate_signal_enhanced()` returns TradingSignal-compatible output

- [ ] **Step 2: Run test — verify FAIL**
- [ ] **Step 3: Implement MantisAgentOrchestrator**

```python
class MantisAgentOrchestrator:
    """
    Coordinates the multi-agent pipeline.
    Flow:
    1. TechnicalAnalyst.analyze() → TechnicalReport
    2. SentimentAnalyst.analyze() → SentimentReport
    3. RiskManager.analyze() → RiskReport
    4. TraderAgent.propose(technical, sentiment, risk) → TradeProposal
    5. BullBearDebate.debate(proposal, technical, sentiment) → DebateSummary
    6. FundManager.decide(proposal, debate, risk) → FinalDecision
    """

    def __init__(self, config: AgentConfig | None = None):
        self.technical = TechnicalAnalystAgent(...)
        self.sentiment = SentimentAnalystAgent(...)
        self.risk = RiskManagerAgent(...)
        self.trader = TraderAgent(...)
        self.debate = BullBearDebate(...)

    async def run(self, context: MarketContext) -> FinalDecision:
        ...
```

Key design:
- Each agent failure is caught and logged — pipeline continues with available data
- If TechnicalReport is None → use defaults (NEUTRAL, 0.5 strength)
- If RiskReport blocks → short-circuit to HOLD
- FinalDecision.agent_audit_trail records each agent's output + timing
- `generate_signal_enhanced()` maps FinalDecision → TradingSignal for backward compat

- [ ] **Step 4: Run tests — verify PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add MantisAgentOrchestrator with full pipeline"
```

---

### Task 1.10: Config + requirements_evolution.txt + .env.example

**Files:**
- Create: `backend/requirements_evolution.txt`
- Modify: `backend/src/utils/config.py` (add agents config section)

- [ ] **Step 1: Create requirements_evolution.txt**

```
anthropic>=0.40.0
```

- [ ] **Step 2: Add AgentConfig to config.py**

```python
# In config.py, add:
# Agent system
agents_enabled: bool = Field(default=False, alias="AGENTS_ENABLED")
agents_llm_model: str = Field(default="claude-sonnet-4-20250514", alias="AGENTS_LLM_MODEL")
agents_temperature: float = Field(default=0.2, alias="AGENTS_TEMPERATURE")
agents_max_tokens: int = Field(default=2000, alias="AGENTS_MAX_TOKENS")
agents_technical_weight: float = Field(default=0.4, alias="AGENTS_TECHNICAL_WEIGHT")
agents_sentiment_weight: float = Field(default=0.2, alias="AGENTS_SENTIMENT_WEIGHT")
agents_risk_weight: float = Field(default=0.4, alias="AGENTS_RISK_WEIGHT")
agents_risk_block_threshold: float = Field(default=0.8, alias="AGENTS_RISK_BLOCK_THRESHOLD")
agents_debate_enabled: bool = Field(default=True, alias="AGENTS_DEBATE_ENABLED")
```

- [ ] **Step 3: Update `.env.example`** — add `ANTHROPIC_API_KEY=`, `AGENTS_ENABLED=false`
- [ ] **Step 4: Add `__init__.py` with clean exports**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agents): add config section + requirements_evolution.txt + .env.example"
```

---

### Task 1.11: MIGRATION_NOTE.md

**Files:**
- Create: `docs/MIGRATION_NOTE.md`

- [ ] **Step 1: Write migration note**

Document:
- `MantisAgentOrchestrator` is OPTIONAL — existing `generate_signal()` flow is untouched
- Set `AGENTS_ENABLED=true` to activate the multi-agent pipeline
- When enabled, orchestrator runs ALONGSIDE XGBoost (not replacing it)
- New dependency: `anthropic` SDK (requires `ANTHROPIC_API_KEY` env var)
- No database schema changes in Sprint 1

- [ ] **Step 2: Commit**

```bash
git commit -m "docs: add MIGRATION_NOTE.md for multi-agent evolution"
```

---

## Sprint 2: Reinforcement Learning

### Task 2.1: RL Schemas + Config

**Files:**
- Create: `backend/src/rl/__init__.py`, `backend/src/rl/schemas.py`
- Test: `backend/tests/rl/test_schemas.py` (optional — thin models)
- Modify: `backend/src/utils/config.py`

- [ ] **Step 1: Create RL schemas** (RLConfig, EnvState, RLSignal)
- [ ] **Step 2: Add RL config to config.py**

```python
# RL system
rl_enabled: bool = Field(default=False, alias="RL_ENABLED")
rl_algorithm: str = Field(default="PPO", alias="RL_ALGORITHM")
rl_reward_function: str = Field(default="composite", alias="RL_REWARD_FUNCTION")
rl_reward_weights: dict = Field(default={"scalping": 0.4, "sharpe": 0.4, "risk_adjusted": 0.2})
rl_sliding_window_size: int = Field(default=500, alias="RL_SLIDING_WINDOW_SIZE")
rl_retrain_interval_minutes: int = Field(default=60, alias="RL_RETRAIN_INTERVAL")
rl_max_trades_per_session: int = Field(default=20)
rl_target_hold_candles: int = Field(default=10)
rl_max_drawdown_pct: float = Field(default=0.01)
```

- [ ] **Step 3: Commit**

---

### Task 2.2: RL Environment

**Files:**
- Create: `backend/src/rl/environment.py`
- Test: `backend/tests/rl/test_environment.py`

- [ ] **Step 1: Write tests** — env passes `check_env()`, correct action/observation spaces, step returns valid tuple
- [ ] **Step 2: Run tests — FAIL**
- [ ] **Step 3: Implement MantisRLEnvironment** — 5 discrete actions, state = [features + position_info + regime]
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

---

### Task 2.3: Reward Functions

**Files:**
- Create: `backend/src/rl/reward_functions.py`
- Test: `backend/tests/rl/test_reward_functions.py`

- [ ] **Step 1: Write tests** — sharpe_reward, scalping_reward (penalizes drawdown>1%), risk_adjusted_reward, composite
- [ ] **Step 2: Run tests — FAIL**
- [ ] **Step 3: Implement MantisRewardCalculator** — 3 functions + weighted composite
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

---

### Task 2.4: Adaptive Trainer

**Files:**
- Create: `backend/src/rl/adaptive_trainer.py`
- Test: `backend/tests/rl/test_adaptive_trainer.py`

- [ ] **Step 1: Write tests** — background thread doesn't block, model hot-swap, sliding window
- [ ] **Step 2: Run tests — FAIL**
- [ ] **Step 3: Implement MantisAdaptiveTrainer** — PPO/SAC support, thread-safe model access, versioned models
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

---

### Task 2.5: RL Agent + Feature Pipeline

**Files:**
- Create: `backend/src/rl/rl_agent.py`, `backend/src/rl/feature_pipeline.py`
- Test: `backend/tests/rl/test_rl_agent.py`

- [ ] **Step 1: Write tests** — MantisRLAgent.analyze() returns RLSignal, feature_pipeline normalizes correctly
- [ ] **Step 2: Run tests — FAIL**
- [ ] **Step 3: Implement** — RL agent wraps into MantisBaseAgent interface, feature pipeline adds `rl_` prefixed features
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Update requirements_evolution.txt** — add `stable-baselines3[extra]`, `gymnasium`, `shimmy` (the `[extra]` variant includes TD3 deps needed in Sprint 5)
- [ ] **Step 6: Commit**

---

## Sprint 3: Layered Memory System

### Task 3.1: Memory Schemas + SQLite Schema

**Files:**
- Create: `backend/src/memory_layer/__init__.py`, `schemas.py`, `schema.sql`
- Test: `backend/tests/memory_layer/test_schemas.py`

- [ ] **Step 1: Create memory schemas** (MemoryItem, TradeOutcome, MarketPattern, Episode, MemoryContext, etc.)
- [ ] **Step 2: Create schema.sql** for SQLite (long_term_patterns, episodes tables)
- [ ] **Step 3: Create `backend/src/memory_layer/migrations/001_initial.sql`** — initial migration script
- [ ] **Step 4: Commit**

---

### Task 3.2: Short Term Memory

**Files:**
- Create: `backend/src/memory_layer/short_term.py`
- Test: `backend/tests/memory_layer/test_short_term.py`

- [ ] **Step 1: Write tests** — add/retrieve items, decay after N hours, win rate calculation, buffer overflow, pickle save/load
- [ ] **Step 2: Implement** — circular buffer, exponential decay (λ=0.1), max 50 signals / 20 trades
- [ ] **Step 3: Add persistence** — Redis if available (graceful degradation), otherwise pickle snapshot to `data/memory/stm_snapshot.pkl`
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

---

### Task 3.3: Long Term Memory

**Files:**
- Create: `backend/src/memory_layer/long_term.py`
- Test: `backend/tests/memory_layer/test_long_term.py`

- [ ] **Step 1: Write tests** — consolidation from STM, query by context similarity, blacklist
- [ ] **Step 2: Implement** — SQLite-backed, periodic consolidation, pattern clustering
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 3.4: Episodic Memory

**Files:**
- Create: `backend/src/memory_layer/episodic.py`
- Test: `backend/tests/memory_layer/test_episodic.py`

- [ ] **Step 1: Write tests** — record episodes above significance threshold, recall similar, generate warnings
- [ ] **Step 2: Implement** — SQLite-backed, no decay, significance scoring
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 3.5: Embeddings

**Files:**
- Create: `backend/src/memory_layer/embeddings.py`
- Test: `backend/tests/memory_layer/test_embeddings.py`

- [ ] **Step 1: Write tests** — embed_market_context returns ndarray, cosine_similarity, TF-IDF fallback
- [ ] **Step 2: Implement** — sentence-transformers (MiniLM) primary, TF-IDF fallback
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Update requirements_evolution.txt** — add `sentence-transformers`, `faiss-cpu`
- [ ] **Step 5: Commit**

---

### Task 3.5b: Memory Config

**Files:**
- Modify: `backend/src/utils/config.py`

- [ ] **Step 1: Add memory config fields to config.py**

```python
# Memory system
memory_enabled: bool = Field(default=False, alias="MEMORY_ENABLED")
memory_stm_max_signals: int = Field(default=50, alias="MEMORY_STM_MAX_SIGNALS")
memory_stm_max_trades: int = Field(default=20, alias="MEMORY_STM_MAX_TRADES")
memory_decay_lambda: float = Field(default=0.1, alias="MEMORY_DECAY_LAMBDA")
memory_consolidation_interval_hours: int = Field(default=24, alias="MEMORY_CONSOLIDATION_HOURS")
memory_episodic_significance_threshold: float = Field(default=0.8, alias="MEMORY_EPISODIC_THRESHOLD")
memory_db_path: str = Field(default="data/memory/mantis_memory.db", alias="MEMORY_DB_PATH")
```

- [ ] **Step 2: Update `.env.example`**
- [ ] **Step 3: Commit**

---

### Task 3.6: Memory Store + Orchestrator Integration

**Files:**
- Create: `backend/src/memory_layer/memory_store.py`
- Modify: `backend/src/agents/orchestrator.py` (inject memory context)
- Test: `backend/tests/memory_layer/test_memory_store.py`

- [ ] **Step 1: Write tests** — get_trading_context combines all 3 layers, record_signal/outcome flow
- [ ] **Step 2: Implement MantisMemoryStore** — unified interface, daily consolidation trigger
- [ ] **Step 3: Wire into orchestrator** — memory context injected before agent calls
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

---

## Sprint 4: Vision AI + RAG Pipeline

### Task 4.1: Chart Generator

**Files:**
- Create: `backend/src/vision/__init__.py`, `schemas.py`, `chart_generator.py`
- Test: `backend/tests/vision/test_chart_generator.py`

- [ ] **Step 1: Write tests** — generates PNG bytes, correct dimensions, handles empty data
- [ ] **Step 2: Implement MantisChartGenerator** — mplfinance candlestick + EMA/BB overlays + volume/RSI subplots
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Update requirements_evolution.txt** — add `mplfinance`
- [ ] **Step 5: Commit**

---

### Task 4.1b: Vision + RAG Config

**Files:**
- Modify: `backend/src/utils/config.py`

- [ ] **Step 1: Add vision + RAG config fields**

```python
# Vision AI
vision_enabled: bool = Field(default=False, alias="VISION_ENABLED")
vision_llm_model: str = Field(default="claude-sonnet-4-20250514", alias="VISION_LLM_MODEL")
vision_chart_width: int = Field(default=1200, alias="VISION_CHART_WIDTH")
vision_chart_height: int = Field(default=600, alias="VISION_CHART_HEIGHT")

# RAG Pipeline
rag_enabled: bool = Field(default=False, alias="RAG_ENABLED")
rag_max_context_tokens: int = Field(default=2000, alias="RAG_MAX_CONTEXT_TOKENS")
rag_news_lookback_hours: int = Field(default=4, alias="RAG_NEWS_LOOKBACK_HOURS")
rag_vector_store_path: str = Field(default="data/rag/vector_store", alias="RAG_VECTOR_STORE_PATH")
```

- [ ] **Step 2: Update `.env.example`**
- [ ] **Step 3: Commit**

---

### Task 4.2: Vision Analyzer

**Files:**
- Create: `backend/src/vision/vision_analyzer.py`
- Test: `backend/tests/vision/test_vision_analyzer.py`

- [ ] **Step 1: Write tests** — mock Claude Vision API, parse VisionReport from JSON response, fallback on parse failure
- [ ] **Step 2: Implement MantisVisionAnalyzer** — base64 chart encoding, Claude vision message, JSON parsing
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 4.3: News RAG Ingester

**Files:**
- Create: `backend/src/rag/__init__.py`, `schemas.py`, `news_ingester.py`
- Test: `backend/tests/rag/test_news_ingester.py`

- [ ] **Step 1: Write tests** — ingest deduplicates, lead paragraph extraction, relevance scoring
- [ ] **Step 2: Implement MantisNewsIngester** — reuses existing SIL feed data (no new API calls)
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 4.4: RAG Context Builder

**Files:**
- Create: `backend/src/rag/context_builder.py`
- Test: `backend/tests/rag/test_context_builder.py`

- [ ] **Step 1: Write tests** — builds context string, respects MAX_CONTEXT_TOKENS, includes all sections
- [ ] **Step 2: Implement MantisRAGContextBuilder** — news + macro + COT + memory sections
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 4.5: Vector Store

**Files:**
- Create: `backend/src/rag/vector_store.py`
- Test: `backend/tests/rag/test_vector_store.py`

- [ ] **Step 1: Write tests** — add/search/save/load, similarity > 0.7 for similar docs
- [ ] **Step 2: Implement MantisVectorStore** — FAISS in-memory with disk snapshots
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 4.6: Vision Agent + Orchestrator Wire

**Files:**
- Create: `backend/src/vision/vision_agent.py`
- Modify: `backend/src/agents/orchestrator.py`
- Test: `backend/tests/vision/test_vision_agent.py`

- [ ] **Step 1: Write tests** — vision agent produces VisionSignal, orchestrator includes vision when enabled
- [ ] **Step 2: Implement MantisVisionAgent** — chart gen → vision analyze → RAG context → VisionSignal
- [ ] **Step 3: Wire into orchestrator** (optional step, gated by config)
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

---

### Task 4.7: Chart + RAG API Endpoints

**Files:**
- Create: `backend/src/api/routers/vision.py`
- Modify: `backend/src/api/main.py`

- [ ] **Step 1: Create FastAPI endpoints**

  - `GET /api/vision/chart/{epic}/{timeframe}` → returns PNG bytes (content-type: image/png)
  - `GET /api/rag/context/{epic}` → returns RAGContext JSON
  - `GET /api/vision/analyze/{epic}` → triggers chart gen + vision analysis, returns VisionReport

- [ ] **Step 2: Register router in main.py**
- [ ] **Step 3: Write tests** — mock chart generator, verify PNG response, verify RAG context structure
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(vision): add chart/RAG API endpoints"
```

> **Note:** Angular frontend components for chart visualization and "Context Intelligence" panel are deferred to a separate UI PR, per CLAUDE.md golden rules (backend-focused work first).

---

## Sprint 5: DRL Agent Ensemble

### Task 5.1: DRL Schemas + Base Agent

**Files:**
- Create: `backend/src/drl/__init__.py`, `schemas.py`, `base_drl_agent.py`
- Test: `backend/tests/drl/test_base_drl_agent.py`

- [ ] **Step 1: Write tests** — MantisDRLAgent interface, train/predict/evaluate/save/load
- [ ] **Step 2: Implement MantisDRLAgent ABC** — wraps stable-baselines3 BaseAlgorithm
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 5.1b: DRL Config

**Files:**
- Modify: `backend/src/utils/config.py`

- [ ] **Step 1: Add DRL config fields**

```python
# DRL Ensemble
drl_enabled: bool = Field(default=False, alias="DRL_ENABLED")
drl_algorithms: str = Field(default="PPO,SAC,A2C,TD3", alias="DRL_ALGORITHMS")
drl_voting_mode: str = Field(default="REGIME_ROUTING", alias="DRL_VOTING_MODE")
drl_confidence_threshold: float = Field(default=0.6, alias="DRL_CONFIDENCE_THRESHOLD")
drl_ensemble_weight: float = Field(default=0.25, alias="DRL_ENSEMBLE_WEIGHT")
drl_total_timesteps: int = Field(default=50000, alias="DRL_TOTAL_TIMESTEPS")
drl_retrain_interval_days: int = Field(default=7, alias="DRL_RETRAIN_INTERVAL_DAYS")
drl_train_test_split: float = Field(default=0.8, alias="DRL_TRAIN_TEST_SPLIT")
drl_sliding_window_candles: int = Field(default=2000, alias="DRL_SLIDING_WINDOW_CANDLES")
drl_min_sharpe_for_deploy: float = Field(default=0.5, alias="DRL_MIN_SHARPE_DEPLOY")
drl_max_drawdown_for_deploy: float = Field(default=0.15, alias="DRL_MAX_DD_DEPLOY")
```

- [ ] **Step 2: Update `.env.example`**
- [ ] **Step 3: Commit**

---

### Task 5.2: Four DRL Agents (PPO, SAC, A2C, TD3)

**Files:**
- Create: `backend/src/drl/agents/{__init__,ppo_agent,sac_agent,a2c_agent,td3_agent}.py`
- Test: `backend/tests/drl/test_ppo_agent.py` (representative test, others similar)

- [ ] **Step 1: Write tests** — each agent trains for 100 steps without error, shares interface
- [ ] **Step 2: Implement PPOAgent, SACAgent, A2CAgent, TD3Agent** — each with DEFAULT_CONFIG and best_regime
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 5.3: DRL Ensemble

**Files:**
- Create: `backend/src/drl/ensemble.py`
- Test: `backend/tests/drl/test_ensemble.py`

- [ ] **Step 1: Write tests** — regime routing selects correct agent, weighted vote, all-agree → confidence=1.0
- [ ] **Step 2: Implement MantisDRLEnsemble** — 3 voting modes (REGIME_ROUTING, WEIGHTED_VOTE, CONFIDENCE_GATE)
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 5.4: DRL Trainer + Performance Analyzer

**Files:**
- Create: `backend/src/drl/trainer.py`, `backend/src/drl/performance_analyzer.py`
- Test: `backend/tests/drl/test_trainer.py`, `test_performance_analyzer.py`

- [ ] **Step 1: Write tests** — train_all_agents, evaluate_and_compare, performance metrics (Sharpe, Sortino, etc.)
- [ ] **Step 2: Implement MantisDRLTrainer + MantisPerformanceAnalyzer**
- [ ] **Step 3: Run tests — PASS**
- [ ] **Step 4: Commit**

---

### Task 5.5: DRL Ensemble Agent + Backtester

**Files:**
- Create: `backend/src/drl/drl_ensemble_agent.py`, `backend/src/drl/backtest.py`
- Modify: `backend/src/agents/orchestrator.py`
- Test: `backend/tests/drl/test_backtest.py`

- [ ] **Step 1: Write tests** — ensemble agent integrates with orchestrator, backtester produces result
- [ ] **Step 2: Implement MantisDRLEnsembleAgent + MantisDRLBacktester**
- [ ] **Step 3: Wire into orchestrator** (gated by DRL_ENABLED config)
- [ ] **Step 4: Run tests — PASS**
- [ ] **Step 5: Commit** (`stable-baselines3[extra]` already added in Sprint 2)

---

## Integration Phase

### Task 6.1: Wire Orchestrator into Paper Loop

**Files:**
- Modify: `backend/src/trading/paper_loop.py`

- [ ] **Step 1: Add optional orchestrator path in `_process_epic()`**

```python
# In _process_epic(), after existing signal generation:
if self._agents_enabled and self._orchestrator:
    # Run multi-agent pipeline alongside existing
    agent_decision = await self._orchestrator.run(market_context)
    if agent_decision and agent_decision.approved:
        # Enhance existing signal with agent insights
        signal.metadata["agent_decision"] = agent_decision.model_dump()
        # Optionally adjust confidence based on agent consensus
```

- [ ] **Step 2: The existing pipeline is UNTOUCHED** — agent system runs in parallel, enriches metadata
- [ ] **Step 3: Commit**

---

### Task 6.2: API Endpoints

**Files:**
- Create: `backend/src/api/routers/agents.py`
- Modify: `backend/src/api/main.py`

- [ ] **Step 1: Create endpoints**
  - `GET /api/agents/status` — agent system status
  - `POST /api/agents/analyze/{epic}` — trigger manual agent analysis
  - `GET /api/agents/last-decision/{epic}` — last FinalDecision for epic

- [ ] **Step 2: Register router in main.py**
- [ ] **Step 3: Commit**

---

### Task 6.3: Integration Tests

**Files:**
- Create: `backend/tests/test_integration_agents.py`

- [ ] **Step 1: Write integration test** — mock LLM, feed real market data fixture, verify full pipeline produces FinalDecision
- [ ] **Step 2: Run all tests** — `pytest tests/ -v --tb=short`
- [ ] **Step 3: Commit**

---

## Validation Phase

### Task 7.1: Smoke Test

- [ ] **Step 1: Run full test suite** — `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short -x`
- [ ] **Step 2: Verify 0 failures in new tests**
- [ ] **Step 3: Verify existing tests still pass** (no regression)

---

### Task 7.2: Finalize Documentation

- [ ] **Step 1: Update MIGRATION_NOTE.md** with all 5 sprints documented
- [ ] **Step 2: Update docs/MIGRATION_NOTE.md** with env vars and config
- [ ] **Step 3: Verify requirements_evolution.txt is complete and installable**
- [ ] **Step 4: Final commit**

```bash
git commit -m "docs: finalize evolution migration notes and requirements"
```

---

## Summary

| Sprint | Tasks | Files Created | Key Deliverable |
|--------|-------|--------------|-----------------|
| 1 | 1.1-1.11 | 10 src + 9 test | MantisAgentOrchestrator + FundManager |
| 2 | 2.1-2.5 | 7 src + 5 test | MantisRLEnvironment + AdaptiveTrainer |
| 3 | 3.1-3.6 | 9 src + 5 test | MantisMemoryStore (3-layer + persistence) |
| 4 | 4.1-4.7 | 11 src + 6 test | Vision AI + RAG pipeline + API endpoints |
| 5 | 5.1-5.5 | 11 src + 6 test | DRL Ensemble (4 agents) |
| Integration | 6.1-6.3 | 1 src + 1 test | Pipeline wiring |
| Validation | 7.1-7.2 | 0 | Smoke test + docs |

**Total: ~49 source files, ~32 test files, ~38 tasks**

**Design notes:**
- FundamentalsAnalyst intentionally excluded: MANTIS trades crypto/forex where traditional fundamentals are less applicable; macro data is covered by the RAG pipeline (Sprint 4) via FRED/COT SIL feeds.
- `mantis/core/pipeline.py` from the ORCHESTRATOR spec is replaced by direct wiring in `paper_loop.py` to avoid adding unnecessary abstraction layers.
- `mantis/sil/` from the spec maps to existing `backend/src/external/` + `backend/src/features/sil_features.py`.

**Critical invariant:** The existing XGBoost pipeline (`ScalpScoreStrategy` → `SignalGenerator` → `RiskManager`) is NEVER modified. The agent system runs in parallel and enriches the existing flow. Toggle with `AGENTS_ENABLED=true`.
