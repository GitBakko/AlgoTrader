# MANTIS AI — Evolution Migration Note

> Branch: `feature/evolution-multi-agent`
> Date: 2026-03-23
> Scope: Sprints 1-5 + Integration Phase

---

## Overview

This migration adds 5 new packages to MANTIS AI, transforming it from a single-model XGBoost system into a multi-agent, memory-aware, RL-enhanced platform with vision AI and DRL ensemble capabilities.

**Critical invariant: The existing XGBoost pipeline is UNTOUCHED.** All new systems run in parallel and enrich the existing flow via feature flags.

---

## New Packages

| Package | Location | Feature Flag | Purpose |
|---------|----------|-------------|---------|
| `agents/` | `backend/src/agents/` | `AGENTS_ENABLED` | Multi-agent orchestrator (6 agents + debate + fund manager) |
| `rl/` | `backend/src/rl/` | `RL_ENABLED` | Gymnasium RL environment + adaptive trainer |
| `memory_layer/` | `backend/src/memory_layer/` | `MEMORY_ENABLED` | 3-layer memory (STM/LTM/Episodic) with SQLite |
| `vision/` | `backend/src/vision/` | `VISION_ENABLED` | Chart generation + Claude Vision analysis |
| `rag/` | `backend/src/rag/` | `RAG_ENABLED` | News ingestion + vector store + context builder |
| `drl/` | `backend/src/drl/` | `DRL_ENABLED` | DRL ensemble (PPO/SAC/A2C/TD3) + trainer + backtester |

---

## New Environment Variables

### Sprint 1: Multi-Agent Architecture
```env
AGENTS_ENABLED=false              # Master toggle for multi-agent system
AGENTS_LLM_MODEL=claude-sonnet-4-20250514  # Claude model for LLM-backed agents
AGENTS_DEBATE_ENABLED=true        # Enable bull/bear debate step
```

### Sprint 2: Reinforcement Learning
```env
RL_ENABLED=false                  # Master toggle for RL
RL_ALGORITHM=PPO                  # SB3 algorithm
RL_TOTAL_TIMESTEPS=50000          # Training timesteps
RL_RETRAIN_INTERVAL_HOURS=168     # Weekly retraining
```

### Sprint 3: Layered Memory
```env
MEMORY_ENABLED=false              # Master toggle for memory system
MEMORY_DB_PATH=data/memory/mantis_memory.db
MEMORY_CONSOLIDATION_HOURS=24
MEMORY_EPISODIC_THRESHOLD=0.8
```

### Sprint 4: Vision AI + RAG
```env
VISION_ENABLED=false              # Master toggle for Vision AI
VISION_LLM_MODEL=claude-sonnet-4-20250514
VISION_CHART_WIDTH=1200
VISION_CHART_HEIGHT=600
RAG_ENABLED=false                 # Master toggle for RAG
RAG_MAX_CONTEXT_TOKENS=2000
RAG_NEWS_LOOKBACK_HOURS=4
RAG_VECTOR_STORE_PATH=data/rag/vector_store
```

### Sprint 5: DRL Ensemble
```env
DRL_ENABLED=false                 # Master toggle for DRL ensemble
DRL_ALGORITHMS=PPO,SAC,A2C,TD3
DRL_VOTING_MODE=REGIME_ROUTING    # REGIME_ROUTING | WEIGHTED_VOTE | CONFIDENCE_GATE
DRL_CONFIDENCE_THRESHOLD=0.6
DRL_ENSEMBLE_WEIGHT=0.25
DRL_TOTAL_TIMESTEPS=50000
DRL_RETRAIN_INTERVAL_DAYS=7
DRL_TRAIN_TEST_SPLIT=0.8
DRL_SLIDING_WINDOW_CANDLES=2000
DRL_MIN_SHARPE_DEPLOY=0.5
DRL_MAX_DD_DEPLOY=0.15
```

---

## New Dependencies

All new dependencies are in `backend/requirements_evolution.txt` (separate from main `requirements.txt`):

```
anthropic>=0.40.0                # Sprint 1: Claude API
stable-baselines3[extra]>=2.3.0 # Sprint 2+5: RL/DRL algorithms
gymnasium>=1.0.0                 # Sprint 2+5: RL environments
shimmy>=2.0.0                    # Sprint 2: gymnasium compatibility
sentence-transformers>=3.0.0     # Sprint 3: embeddings
faiss-cpu>=1.8.0                 # Sprint 3: vector search
mplfinance>=0.12.10b0            # Sprint 4: chart generation
matplotlib>=3.10.0               # Sprint 4: chart rendering
```

Install: `pip install -r requirements_evolution.txt`

---

## New API Endpoints

| Method | Path | Feature Flag | Description |
|--------|------|-------------|-------------|
| GET | `/api/agents/status` | — | Agent system status |
| POST | `/api/agents/analyze/{epic}` | `AGENTS_ENABLED` | Manual agent analysis |
| GET | `/api/agents/last-decision/{epic}` | `AGENTS_ENABLED` | Last agent decision |
| GET | `/api/vision/status` | — | Vision + RAG config |
| POST | `/api/vision/chart` | — | Generate chart PNG |
| POST | `/api/vision/analyze` | `VISION_ENABLED` | Vision AI analysis |
| GET | `/api/vision/rag` | `RAG_ENABLED` | RAG context snapshot |
| GET | `/api/drl/status` | — | DRL ensemble config |
| GET | `/api/drl/ensemble` | `DRL_ENABLED` | Ensemble agent status |
| POST | `/api/drl/predict` | `DRL_ENABLED` | Manual DRL prediction |

---

## Breaking Changes

**None.** All new features are behind feature flags (disabled by default). The existing XGBoost pipeline, API contracts, and database schema are completely unchanged.

---

## Orchestrator Pipeline Flow

When `AGENTS_ENABLED=true`, the orchestrator runs after each successful trade execution:

```
Step 1: TechnicalAnalyst.analyze(context) → TechnicalReport
Step 2: SentimentAnalyst.analyze(context) → SentimentReport
Step 3: RiskManager.analyze(context) → RiskReport
Step 3b: [VISION_ENABLED] VisionAgent.analyze(context) → VisionSignal
Step 3c: [DRL_ENABLED] DRLEnsembleAgent.analyze(context) → DRLEnsembleSignal
Step 4: TraderAgent.propose(tech, sent, risk, context) → TradeProposal
Step 5: [DEBATE_ENABLED] BullBearDebate.debate(proposal, ...) → DebateSummary
Step 6: FundManager.decide(proposal, debate, risk) → FinalDecision
```

The FinalDecision is stored in `signal_info["agent_decision"]` metadata — it enriches but never blocks the existing signal.

---

## Test Summary

| Area | Tests | Status |
|------|-------|--------|
| Sprint 1: Agents | ~120 | Pass |
| Sprint 2: RL | ~60 | Pass |
| Sprint 3: Memory | ~50 | Pass |
| Sprint 4: Vision + RAG | 97 | Pass |
| Sprint 5: DRL | 126 | Pass |
| Integration | 7 | Pass |
| Full suite | 2251 | Pass (excl. 3 pre-existing ORB+FVG) |
