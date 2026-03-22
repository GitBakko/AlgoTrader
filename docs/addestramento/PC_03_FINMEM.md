# MANTIS AI — PROMPT CONTRACT 03
## Sprint: Layered Memory System
## Sorgente: `pipiku915/FinMem-LLM-StockTrading`

---

## 🎯 OBIETTIVO SPRINT

Dotare MANTIS di un sistema di **memoria stratificata** ispirato alla struttura cognitiva
umana del trader. MANTIS attualmente non ha memoria tra sessioni — ogni ciclo di trading
riparte da zero. Questo sprint introduce 3 livelli di memoria (breve termine, lungo termine,
episodica) che permettono al sistema di imparare da trade passati, ricordare pattern di mercato
ricorrenti e costruire una base di conoscenza che cresce nel tempo.

**Impatto atteso:** riduzione degli errori ripetuti, riconoscimento di pattern storici,
personalizzazione della strategia basata sull'esperienza accumulata.

---

## 📂 NAVIGAZIONE REPO SORGENTE

```bash
gh repo clone pipiku915/FinMem-LLM-StockTrading /tmp/source_repos/FinMem/
```

### File chiave da analizzare (in ordine):
```
FinMem-LLM-StockTrading/
├── finmem/
│   ├── memory/
│   │   ├── base_memory.py          ← PRIORITÀ 1: struttura base memoria
│   │   ├── short_term_memory.py    ← PRIORITÀ 1: memoria breve termine
│   │   ├── long_term_memory.py     ← PRIORITÀ 1: memoria lungo termine
│   │   └── memory_manager.py      ← PRIORITÀ 1: coordinamento livelli
│   ├── profiling/
│   │   └── agent_profile.py        ← PRIORITÀ 2: profilo agente/personalità
│   ├── decision/
│   │   └── decision_maker.py       ← PRIORITÀ 2: come la memoria influenza decisioni
│   └── utils/
│       └── embedding.py            ← PRIORITÀ 3: sistema di embedding per retrieval
├── config/
│   └── config.yaml                 ← PRIORITÀ 2: parametri di configurazione
└── README.md
```

### Cosa estrarre:
1. **Schema a 3 livelli** di memoria (short/long/episodic)
2. **Meccanismo di retrieval** semantico (embedding-based)
3. **Pattern di decay temporale** per la memoria breve termine
4. **Struttura del "trade memory"** (cosa ricordare di ogni trade)
5. **Come la memoria influenza la decision-making** (non è solo log — è input attivo)

---

## 🏗️ TASK DI IMPLEMENTAZIONE

### Task 3.1 — Short Term Memory
Crea `mantis/memory/short_term.py`:

```python
class MantisShortTermMemory:
    """
    Memoria a breve termine: contiene gli ultimi N eventi di mercato
    e le ultime M decisioni di trading con i loro outcome.
    
    Ispirata a FinMem: usa un buffer circolare con decay esponenziale.
    
    Cosa ricorda:
    - Ultimi 50 segnali generati (con timestamp e outcome se disponibile)
    - Ultimi 20 trades (entry, exit, P&L, durata)
    - Pattern di mercato recenti (regime, volatilità, trend)
    - Errori recenti (false positives, missed entries)
    
    Decay: gli item invecchiano con un peso esponenziale e:t = e^(-λ * age_hours)
    Default λ = 0.1 (dimezza il peso in ~7 ore)
    """
    
    max_signals: int = 50
    max_trades: int = 20
    decay_lambda: float = 0.1
    
    def add_signal(self, signal: FinalDecision, outcome: Optional[TradeOutcome] = None):
        ...
    
    def add_trade_outcome(self, trade_id: str, outcome: TradeOutcome):
        """Aggiorna un segnale con il suo outcome reale."""
        ...
    
    def get_recent_context(self, n: int = 10) -> list[MemoryItem]:
        """Ritorna gli N item più recenti e rilevanti (con peso decay)."""
        ...
    
    def get_win_rate_recent(self, window_hours: float = 24) -> float:
        """Win rate nelle ultime N ore — utile per confidence adjustment."""
        ...
```

### Task 3.2 — Long Term Memory
Crea `mantis/memory/long_term.py`:

```python
class MantisLongTermMemory:
    """
    Memoria a lungo termine: pattern e conoscenza consolidata nel tempo.
    Persistita su SQLite (o PostgreSQL se disponibile nel progetto).
    
    Cosa ricorda:
    - Pattern di mercato con alta frequenza storica (es: "BTC cala il lunedì mattina")
    - Configurazioni di indicatori che hanno funzionato bene in certi regimi
    - Correlazioni storiche tra segnali SIL e outcome dei trade
    - Blacklist di condizioni (pattern che storicamente producono perdite)
    
    Ispirata a FinMem: la LTM si aggiorna periodicamente (ogni 24h)
    attraverso un processo di "consolidation" che estrae pattern dalla STM.
    """
    
    def consolidate(self, short_term: MantisShortTermMemory):
        """
        Processo di consolidazione giornaliera.
        Estrae pattern significativi dalla STM e li promuove a LTM.
        Usa clustering su feature vector per identificare pattern ricorrenti.
        """
        ...
    
    def query(self, current_context: MarketContext, top_k: int = 5) -> list[LTMEntry]:
        """
        Semantic search: trova i pattern storici più simili alla situazione attuale.
        Usa embedding cosine similarity.
        """
        ...
    
    def add_pattern(self, pattern: MarketPattern, outcome: PatternOutcome):
        """Aggiunge manualmente un pattern alla LTM."""
        ...
    
    def get_blacklist(self) -> list[BlacklistCondition]:
        """Pattern da evitare basati su performance storica negativa."""
        ...
```

### Task 3.3 — Episodic Memory
Crea `mantis/memory/episodic.py`:

```python
class MantisEpisodicMemory:
    """
    Memoria episodica: ricorda "episodi" specifici ad alto impatto.
    
    Un episodio è un evento di mercato memorabile:
    - Trade con P&L eccezionale (top 5% o bottom 5%)
    - Flash crash / pump improvvisi
    - Condizioni di mercato estreme (Fear&Greed < 15 o > 85)
    - Trade dove il sistema ha sbagliato nonostante alta confidence
    
    Gli episodi NON decadono — rimangono disponibili indefinitamente
    come "lezioni apprese".
    
    Ispirata a FinMem: la memoria episodica è il meccanismo principale
    per l'auto-evoluzione del sistema.
    """
    
    significance_threshold: float = 0.8  # score minimo per diventare episodio
    
    def record_episode(self, event: MarketEvent, context: MarketContext,
                       outcome: TradeOutcome, significance: float):
        """Registra un episodio se supera la soglia di significatività."""
        ...
    
    def recall_similar(self, current_context: MarketContext, 
                       top_k: int = 3) -> list[Episode]:
        """
        Richiama gli episodi più simili al contesto attuale.
        Usa distanza coseno su embedding del contesto.
        """
        ...
    
    def get_warnings(self, current_context: MarketContext) -> list[Warning]:
        """
        Genera warning basati su episodi negativi simili al passato.
        Es: "Situazione simile al crash del 2024-03-15 — max size ridotta del 50%"
        """
        ...
```

### Task 3.4 — Memory Store (Coordinatore)
Crea `mantis/memory/memory_store.py`:

```python
class MantisMemoryStore:
    """
    Coordinatore centrale della memoria MANTIS.
    Espone un'interfaccia unificata per leggere e scrivere in tutti e 3 i livelli.
    
    Questo è l'oggetto che gli agenti (Sprint 1) utilizzano.
    """
    
    def __init__(self, config: MemoryConfig, db_path: Path):
        self.short_term = MantisShortTermMemory(...)
        self.long_term = MantisLongTermMemory(...)
        self.episodic = MantisEpisodicMemory(...)
        self._embedding_model = ...  # vedi Task 3.5
    
    def get_trading_context(self, current_market: MarketContext) -> MemoryContext:
        """
        Metodo principale: ritorna un MemoryContext arricchito da tutti e 3 i livelli.
        Usato dagli agenti prima di prendere decisioni.
        
        Combina:
        - STM: ultimi trade e segnali recenti
        - LTM: pattern storici simili (top 5)
        - Episodic: warning da episodi negativi simili
        """
        ...
    
    def record_signal(self, decision: FinalDecision):
        """Registra una decisione nella STM."""
        ...
    
    def record_outcome(self, trade_id: str, outcome: TradeOutcome):
        """
        Aggiorna la STM con l'outcome reale.
        Triggera promozione a LTM se significativo.
        Triggera creazione episodio se eccezionale.
        """
        ...
    
    def run_daily_consolidation(self):
        """Cron job giornaliero: consolida STM → LTM."""
        ...
```

### Task 3.5 — Embedding per Retrieval Semantico
Crea `mantis/memory/embeddings.py`:

Strategia: usa embedding **leggeri e locali** — no API calls per la memoria.

```python
class MantisEmbedder:
    """
    Genera embedding per il retrieval semantico nella memoria.
    
    Strategia (in ordine di preferenza):
    1. Sentence-transformers con modello piccolo (all-MiniLM-L6-v2, ~22MB)
    2. Fallback: TF-IDF su testo strutturato se transformers non disponibile
    
    L'embedding include:
    - Regime di mercato (codificato come one-hot)
    - Features principali normalizzate (top 20 per XGBoost importance)
    - Sentiment score
    - Timeframe del giorno (mattina/pomeriggio/sera/notte UTC)
    """
    
    def embed_market_context(self, context: MarketContext) -> np.ndarray:
        ...
    
    def embed_text(self, text: str) -> np.ndarray:
        """Per embeddings di testi (rationale, pattern descriptions)."""
        ...
    
    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        ...
```

### Task 3.6 — Integrazione con Sprint 1
Modifica `mantis/agents/orchestrator.py` per iniettare il MemoryContext:

```python
# In MantisAgentOrchestrator.run():
memory_context = self.memory_store.get_trading_context(market_context)

# Inietta in tutti gli agenti che ne beneficiano:
# - TechnicalAnalyst: usa LTM per confrontare con pattern storici
# - RiskManager: usa Episodic warnings per aggiustare risk score
# - TraderAgent: usa STM per evitare overtrading
```

### Task 3.7 — Persistenza
- Usa SQLite per LTM e Episodic (file locale, no dipendenze esterne)
- Usa Redis per STM se disponibile, altrimenti in-memory con pickle snapshot
- Schema SQLite in `mantis/memory/schema.sql`
- Migration script in `mantis/memory/migrations/`

---

## 📊 SCHEMA DATI CHIAVE

```python
class TradeOutcome(BaseModel):
    trade_id: str
    entry_price: float
    exit_price: float
    pnl_pct: float
    duration_candles: int
    max_drawdown_during: float
    exit_reason: Literal["TP", "SL", "MANUAL", "TIMEOUT"]

class MarketPattern(BaseModel):
    pattern_id: str
    description: str
    feature_signature: np.ndarray  # embedding del contesto
    regime: str
    occurrence_count: int
    avg_outcome: float  # avg P&L quando questo pattern appare
    confidence: float

class Episode(BaseModel):
    episode_id: str
    timestamp: datetime
    description: str
    context_embedding: np.ndarray
    outcome: TradeOutcome
    significance: float
    lesson: str  # generato da LLM durante la registrazione
```

---

## 🧪 TEST RICHIESTI

Crea `tests/test_memory.py`:
- Test decay corretto nella STM dopo N ore
- Test che la consolidazione promuove pattern da STM a LTM
- Test retrieval semantico (similarity > 0.8 per contesti identici)
- Test che gli Episodic warnings bloccano trade in condizioni simili a episodi negativi
- Test persistenza: save + load da SQLite mantiene tutti i dati

---

## ✅ CRITERI DI COMPLETAMENTO SPRINT 3

- [ ] `mantis/memory/` package con tutti i file richiesti
- [ ] `MantisMemoryStore` istanziabile e funzionante
- [ ] STM con decay funzionante
- [ ] LTM con persistenza SQLite
- [ ] Episodic memory con retrieval semantico
- [ ] Integrazione con `MantisAgentOrchestrator` (Sprint 1)
- [ ] `schema.sql` presente e corretto
- [ ] Test passano
- [ ] `requirements_evolution.txt`: `sentence-transformers`, `faiss-cpu`

---

*Sprint 3 di 5 | Dipende da: Sprint 1 | Blocca: Sprint 4 (RAG usa memory store)*
