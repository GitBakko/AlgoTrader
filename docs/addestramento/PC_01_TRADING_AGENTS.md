# MANTIS AI — PROMPT CONTRACT 01
## Sprint: Multi-Agent Architecture
## Sorgente: `TauricResearch/TradingAgents`

---

## 🎯 OBIETTIVO SPRINT

Trasformare MANTIS da un sistema single-model (XGBoost monolitico) a un sistema
**multi-agent specializzato**, dove agenti con ruoli distinti collaborano per produrre
segnali di trading più robusti, esplicabili e con risk management integrato.

**Stima complessità:** Alta — questo sprint introduce il cambiamento architetturale più
significativo. Tutti gli altri sprint si appoggiano ai pattern introdotti qui.

---

## 📂 NAVIGAZIONE REPO SORGENTE

```bash
gh repo clone TauricResearch/TradingAgents /tmp/source_repos/TradingAgents/
```

### File chiave da analizzare (in ordine):
```
TradingAgents/
├── tradingagents/
│   ├── graph/
│   │   └── trading_graph.py          ← PRIORITÀ 1: flow LangGraph tra agenti
│   ├── agents/
│   │   ├── analysts/
│   │   │   ├── technical_analyst.py  ← PRIORITÀ 1: logica analisi tecnica
│   │   │   ├── sentiment_analyst.py  ← PRIORITÀ 2: logica sentiment
│   │   │   └── fundamentals_analyst.py
│   │   ├── researchers/
│   │   │   ├── bull_researcher.py    ← PRIORITÀ 2: pattern debate bull/bear
│   │   │   └── bear_researcher.py
│   │   ├── managers/
│   │   │   ├── risk_manager.py       ← PRIORITÀ 1: logica risk management
│   │   │   └── fund_manager.py       ← PRIORITÀ 1: decisione finale
│   │   └── trader.py                 ← PRIORITÀ 1: execution agent
│   ├── dataflows/
│   │   └── ...                       ← PRIORITÀ 3: struttura dati tra agenti
│   └── default_config.py             ← PRIORITÀ 2: configurazione sistema
└── README.md
```

### Cosa estrarre (NON copiare verbatim):
1. **Pattern di comunicazione strutturata** tra agenti (report JSON, non dialogo libero)
2. **Struttura base della classe Agent** (ruolo, prompt system, output schema)
3. **Logica del debate bull/bear** tra Researcher agents
4. **Criteri di approvazione/rifiuto** del Fund Manager
5. **Schema del trading decision** (timing, size, rationale)

---

## 🏗️ TASK DI IMPLEMENTAZIONE

### Task 1.1 — Base Agent Class
Crea `mantis/agents/base_agent.py`:

```python
# Pattern da seguire (adatta all'architettura MANTIS)
class MantisBaseAgent:
    """
    Agente base MANTIS. Ogni agente produce un StructuredReport,
    NON output in linguaggio libero.
    Usa Claude (via Anthropic API) come LLM interno per reasoning.
    """
    role: AgentRole          # enum: TECHNICAL, SENTIMENT, RISK, TRADER, FUND_MANAGER
    model: str               # default: "claude-sonnet-4-20250514"
    output_schema: BaseModel # Pydantic schema dell'output strutturato
    
    def analyze(self, market_context: MarketContext) -> StructuredReport:
        ...
    
    def get_system_prompt(self) -> str:
        # Ogni agente ha un system prompt specializzato
        ...
```

**Vincoli:**
- Usa `anthropic` SDK Python già presente nel progetto
- Output SEMPRE Pydantic BaseModel, mai dict raw
- Aggiungi `# MANTIS-EVOLUTION: Agent base class` nel header

### Task 1.2 — Technical Analyst Agent
Crea `mantis/agents/technical_analyst.py`:

**Logica da integrare da TradingAgents:**
- Analisi multi-timeframe (non solo il timeframe principale)
- Pattern detection strutturato (non solo indicatori raw)
- Output include: `trend_direction`, `strength_score` (0-1), `key_levels`, `rationale`

**Adattamento MANTIS specifico:**
- Deve consumare le 220+ features già calcolate dal SIL, non ricalcolarle
- Deve riconoscere i regime di mercato già identificati da MANTIS (trending/ranging/volatile)
- Output deve essere compatibile con il formato attuale dei segnali XGBoost

### Task 1.3 — Sentiment Analyst Agent
Crea `mantis/agents/sentiment_analyst.py`:

**Logica da integrare:**
- Aggregazione multi-sorgente (Fear&Greed + StockTwits + news)
- Normalizzazione sentiment score su scala comune [-1, +1]
- Decay temporale: sentiment recente pesa di più

**Adattamento MANTIS specifico:**
- Usa i 6 feed SIL già esistenti come input
- NON chiamare nuove API — usa i dati già fetchati dal SIL pipeline
- Aggiungi campo `confidence` basato sulla consistenza tra sorgenti

### Task 1.4 — Risk Manager Agent
Crea `mantis/agents/risk_manager.py`:

**Logica da integrare da TradingAgents:**
- Valutazione volatilità, liquidità, esposizione corrente
- Report di rischio con `risk_score`, `max_position_size`, `stop_loss_levels`
- Pattern debate: il Risk Manager può **bloccare** una proposta del Trader

**Adattamento MANTIS specifico:**
- Integra con il Kelly Criterion sizing già implementato in MANTIS
- Usa VPIN come proxy di liquidità (già presente nelle features)
- Hard limit: se `risk_score > 0.8` → forza HOLD indipendentemente dal resto

### Task 1.5 — Trader Agent
Crea `mantis/agents/trader_agent.py`:

**Logica da integrare:**
- Combina i report di Technical + Sentiment + Risk in una proposta di trade
- Include: `action` (BUY/SELL/HOLD), `size_pct`, `entry_price`, `tp_levels`, `sl_level`, `rationale`
- Il Trader produce una **proposta**, non una decisione finale

### Task 1.6 — Agent Orchestrator
Crea `mantis/agents/orchestrator.py`:

```python
class MantisAgentOrchestrator:
    """
    Coordina il flow tra agenti. Sostituisce la logica di decision-making
    monolitica attuale di MANTIS.
    
    Flow:
    1. TechnicalAnalyst.analyze() → TechnicalReport
    2. SentimentAnalyst.analyze() → SentimentReport  
    3. [parallel] RiskManager.assess() → RiskReport
    4. TraderAgent.propose(technical, sentiment, risk) → TradeProposal
    5. [debate] BullAgent vs BearAgent review proposal
    6. FundManager.decide(proposal, debate_summary) → FinalDecision
    """
```

**BREAKING CHANGE — documenta in MIGRATION_NOTE.md:**
- La funzione `generate_signal()` esistente in MANTIS diventa un wrapper che chiama
  `MantisAgentOrchestrator.run()` — mantieni la vecchia firma per retrocompatibilità

### Task 1.7 — Bull/Bear Debate Module
Crea `mantis/agents/debate.py`:

Implementa il pattern "structured debate" da TradingAgents:
- BullAgent: analizza perché il trade dovrebbe essere eseguito
- BearAgent: analizza i rischi e perché non dovrebbe
- DebateSummary: sintesi con argomenti pro/contro e confidence score
- Usa temperature=0.2 per riproducibilità

---

## 📊 OUTPUT SCHEMA (Pydantic models)

Crea `mantis/agents/schemas.py` con:

```python
class TechnicalReport(BaseModel):
    timestamp: datetime
    symbol: str
    trend_direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    strength_score: float  # 0.0 - 1.0
    key_support_levels: list[float]
    key_resistance_levels: list[float]
    active_patterns: list[str]
    timeframe_consensus: dict[str, str]  # {"1m": "BULLISH", "5m": "NEUTRAL", ...}
    rationale: str

class SentimentReport(BaseModel):
    timestamp: datetime
    composite_score: float  # -1.0 to +1.0
    fear_greed_index: float
    social_sentiment: float
    news_sentiment: float
    confidence: float  # consistenza tra sorgenti
    dominant_narrative: str

class RiskReport(BaseModel):
    timestamp: datetime
    risk_score: float  # 0.0 - 1.0 (>0.8 = BLOCK)
    volatility_regime: Literal["LOW", "MEDIUM", "HIGH", "EXTREME"]
    max_position_size_pct: float
    recommended_stop_loss_pct: float
    liquidity_score: float  # da VPIN
    blocking: bool  # True = RiskManager ha posto il veto

class TradeProposal(BaseModel):
    timestamp: datetime
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    size_pct: float
    entry_price: float
    take_profit_levels: list[float]
    stop_loss: float
    rationale: str
    source_reports: dict  # refs ai report usati

class FinalDecision(TradeProposal):
    approved: bool
    override_reason: Optional[str]
    debate_summary: Optional[str]
    agent_audit_trail: list[dict]  # log completo delle decisioni agenti
```

---

## 🧪 TEST RICHIESTI

Crea `tests/test_agents.py`:
- Test unitario per ogni agente con mock del LLM (usa `anthropic` mock)
- Test del flow orchestrator end-to-end con dati fixture BTC/USDT
- Test che verifica il blocco del RiskManager quando `risk_score > 0.8`
- Test che il FinalDecision.agent_audit_trail sia sempre popolato

---

## ✅ CRITERI DI COMPLETAMENTO SPRINT 1

- [ ] `mantis/agents/` package con tutti i file richiesti
- [ ] Tutti gli schema Pydantic definiti e validati
- [ ] `MantisAgentOrchestrator.run()` produce un `FinalDecision` valido
- [ ] `generate_signal()` legacy è un wrapper compatibile
- [ ] Test passano
- [ ] `MIGRATION_NOTE.md` documenta il breaking change
- [ ] Nessuna chiamata API aggiuntiva oltre all'Anthropic SDK

---

*Sprint 1 di 5 | Dipendenze: nessuna | Blocca: Sprint 2, 3, 5*
