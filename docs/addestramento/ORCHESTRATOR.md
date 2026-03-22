# MANTIS AI — EVOLUTION ORCHESTRATOR
## Prompt Contract v1.0 | Claude Code Master Controller

---

## 🎯 MISSIONE

Questo file è il **punto di ingresso unico** per la fase di evoluzione di MANTIS AI.
Il tuo compito è coordinare l'esecuzione sequenziale di 5 sprint specializzati, ognuno mappato
a una repo GitHub sorgente, per portare MANTIS da Phase 22 a un sistema multi-agent,
memory-aware, reinforcement-learning-driven, con vision AI e context intelligence avanzato.

**Repository MANTIS di riferimento:** `github.com/GitBakko/AlgoTrader`

---

## 📦 SPRINT MAP

| Sprint | File Contract | Repo Sorgente | Area di Impatto |
|--------|---------------|---------------|-----------------|
| 1 | `PC_01_TRADING_AGENTS.md` | TauricResearch/TradingAgents | Architettura multi-agent |
| 2 | `PC_02_FREQAI.md` | freqtrade/freqtrade (FreqAI) | RL + adaptive retraining |
| 3 | `PC_03_FINMEM.md` | pipiku915/FinMem-LLM-StockTrading | Layered memory system |
| 4 | `PC_04_LLM_TRADER.md` | qrak/LLM_trader | Vision AI + RAG pipeline |
| 5 | `PC_05_FINRL.md` | AI4Finance-Foundation/FinRL | DRL agent ensemble |

---

## ⚙️ REGOLE GLOBALI (si applicano a TUTTI gli sprint)

### Architettura MANTIS attuale — NON rompere questi contratti
```
Stack:     Python/FastAPI backend | Angular frontend | Polars data | XGBoost classifier
Broker:    Capital.com (REST + WebSocket)
SIL APIs:  Fear&Greed, FRED, Alpha Vantage, CFTC COT, StockTwits, Finnhub
Features:  220+ (OFI, VPIN, Hawkes Processes, COT data)
Target:    BTC/USDT perpetual futures (Bybit), scalping + swing
```

### Principi DRY e Anti-Drift
- NON duplicare logica esistente — estendi, non riscrivi
- NON cambiare il contratto dei moduli XGBoost esistenti senza migration script
- OGNI breaking change deve avere un `MIGRATION_NOTE.md` nello stesso PR
- Usa `# MANTIS-EVOLUTION:` come tag nei commenti per marcare codice nuovo

### Pattern di navigazione repo esterne
Per ogni repo sorgente:
1. `gh repo clone <repo>` in `/tmp/source_repos/<repo_name>/`
2. Leggi prima `README.md` e la struttura delle directory
3. Identifica i file chiave elencati nel singolo prompt contract
4. Estrai la logica — NON copiare codice verbatim, **adatta all'architettura MANTIS**
5. Rimuovi la repo clonata dopo l'integrazione per pulizia

### Gestione dipendenze
- Aggiungi tutte le nuove dipendenze in `requirements_evolution.txt` (file separato)
- NON modificare il `requirements.txt` principale senza conferma esplicita
- Preferisci librerie già nel progetto dove possibile

---

## 🔄 FLOW DI ESECUZIONE

```
START
  │
  ▼
[Pre-check] Verifica struttura MANTIS locale
  │         git status, leggi CLAUDE.md esistente, mappa moduli attuali
  │
  ▼
[Sprint 1] PC_01_TRADING_AGENTS.md
  │         Output: mantis/agents/ package + AgentOrchestrator
  │
  ▼
[Sprint 2] PC_02_FREQAI.md
  │         Output: mantis/rl/ package + AdaptiveTrainer
  │         Dipende da: Sprint 1 (usa AgentOrchestrator per coordinare RL)
  │
  ▼
[Sprint 3] PC_03_FINMEM.md
  │         Output: mantis/memory/ package + LayeredMemoryStore
  │         Dipende da: Sprint 1 (gli agenti usano la memoria)
  │
  ▼
[Sprint 4] PC_04_LLM_TRADER.md
  │         Output: mantis/vision/ + mantis/rag/ packages
  │         Dipende da: Sprint 3 (RAG usa LayeredMemoryStore)
  │
  ▼
[Sprint 5] PC_05_FINRL.md
  │         Output: mantis/drl/ package + DRLEnsemble
  │         Dipende da: Sprint 1+2 (agenti + RL coordinator)
  │
  ▼
[Integration] Wiring finale
  │         Aggiorna mantis/core/pipeline.py
  │         Aggiorna mantis/api/routes.py
  │         Scrivi test di integrazione
  │
  ▼
[Validation] Backtesting smoke test su dati storici BTC/USDT
  │
  ▼
END → Aggiorna CLAUDE.md principale con nuova architettura
```

---

## 📁 STRUTTURA TARGET POST-EVOLUZIONE

```
mantis/
├── agents/                    # [NEW - Sprint 1] Multi-agent system
│   ├── base_agent.py
│   ├── technical_analyst.py
│   ├── sentiment_analyst.py
│   ├── risk_manager.py
│   ├── trader_agent.py
│   └── orchestrator.py
├── rl/                        # [NEW - Sprint 2] Reinforcement learning
│   ├── environment.py
│   ├── reward_functions.py
│   ├── adaptive_trainer.py
│   └── models/
├── memory/                    # [NEW - Sprint 3] Layered memory
│   ├── short_term.py
│   ├── long_term.py
│   ├── episodic.py
│   └── memory_store.py
├── vision/                    # [NEW - Sprint 4] Chart vision AI
│   ├── chart_generator.py
│   └── vision_analyzer.py
├── rag/                       # [NEW - Sprint 4] RAG pipeline
│   ├── news_ingester.py
│   ├── vector_store.py
│   └── context_builder.py
├── drl/                       # [NEW - Sprint 5] Deep RL ensemble
│   ├── agents/                # A2C, PPO, SAC, TD3
│   ├── ensemble.py
│   └── trainer.py
├── core/                      # [EXISTING - aggiorna]
│   ├── pipeline.py            # Orchestrazione principale
│   └── ...
└── sil/                       # [EXISTING - preserva]
    └── ...
```

---

## ✅ CRITERI DI COMPLETAMENTO GLOBALI

Prima di considerare l'evoluzione completata, verifica:

- [ ] Tutti e 5 i package sono creati e importabili
- [ ] `mantis/core/pipeline.py` integra tutti i nuovi moduli
- [ ] I test smoke passano in dry-run su dati storici
- [ ] `MIGRATION_NOTE.md` documenta tutti i breaking changes
- [ ] `requirements_evolution.txt` è aggiornato e installabile
- [ ] Il CLAUDE.md principale è aggiornato con la nuova architettura
- [ ] Nessun import circolare tra i package

---

## 🚨 STOP CONDITIONS

Fermati e chiedi conferma se:
- Un sprint richiede di riscrivere più del 40% di un modulo esistente
- Una dipendenza nuova è incompatibile con Python 3.11+
- Un breaking change impatta il contratto dell'API FastAPI pubblica
- Il backtesting smoke test produce risultati anomali (Sharpe < -2 o drawdown > 80%)

---

*Generato per MANTIS AI Phase 23+ | Versione Evolution 1.0*
