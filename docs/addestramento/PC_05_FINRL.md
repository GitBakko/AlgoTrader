# MANTIS AI — PROMPT CONTRACT 05
## Sprint: Deep RL Agent Ensemble
## Sorgente: `AI4Finance-Foundation/FinRL`

---

## 🎯 OBIETTIVO SPRINT

Costruire un **ensemble di agenti DRL** (Deep Reinforcement Learning) che lavora in parallelo
all'XGBoost e all'agente RL di Sprint 2, aggiungendo la capacità di ottimizzazione del
portafoglio su più strategie simultanee.

Mentre Sprint 2 (FreqAI) introduce un singolo agente RL adattivo per il trading signal,
questo sprint introduce un **ensemble di 4 agenti DRL** con algoritmi diversi (A2C, PPO, SAC, TD3)
che votano sulla migliore azione — aumentando la robustezza del sistema.

Il principio: algoritmi diversi eccellono in regimi di mercato diversi.
L'ensemble seleziona dinamicamente quale agente seguire in base al regime corrente.

---

## 📂 NAVIGAZIONE REPO SORGENTE

```bash
gh repo clone AI4Finance-Foundation/FinRL /tmp/source_repos/FinRL/
# Clona anche il repo FinRL-Trading per il workflow completo
gh repo clone AI4Finance-Foundation/FinRL-Trading /tmp/source_repos/FinRL-Trading/
```

### File chiave da analizzare (in ordine):
```
FinRL/
├── finrl/
│   ├── agents/
│   │   ├── stablebaselines3/
│   │   │   └── models.py            ← PRIORITÀ 1: wrapper A2C, DDPG, PPO, TD3, SAC
│   │   └── elegantrl/               ← PRIORITÀ 3: alternativa (skip se complessa)
│   ├── meta/
│   │   ├── env_stock_trading/
│   │   │   └── env_stocktrading.py  ← PRIORITÀ 1: ambiente trading completo
│   │   └── data_processors/
│   │       └── processor_alpaca.py  ← PRIORITÀ 2: pattern data processor
│   └── config.py                    ← PRIORITÀ 2: configurazione agenti
├── examples/
│   └── FinRL_Full_Workflow.ipynb    ← PRIORITÀ 1: workflow end-to-end
│
FinRL-Trading/
├── src/
│   ├── strategies/
│   │   └── ml_strategy.py           ← PRIORITÀ 1: ML-based strategy framework
│   ├── backtest/
│   │   └── backtest_engine.py       ← PRIORITÀ 1: backtesting engine
│   └── trading/
│       └── performance_analyzer.py  ← PRIORITÀ 2: metriche performance
└── examples/
    └── FinRL_Full_Workflow.ipynb    ← PRIORITÀ 1: workflow train-test-trade
```

### Cosa estrarre:
1. **Wrapper unificato** per A2C, PPO, SAC, TD3 (stessa interfaccia)
2. **Pipeline train-test-trade** (train su storico, test su OOS, deploy in live)
3. **Metriche di performance** per confronto agenti (Sharpe, Calmar, Sortino, Max DD)
4. **Regime detection** per routing dinamico verso l'agente migliore
5. **Backtesting engine** per validare gli agenti prima del deploy

---

## 🏗️ TASK DI IMPLEMENTAZIONE

### Task 5.1 — DRL Agent Base Interface
Crea `mantis/drl/base_drl_agent.py`:

```python
from abc import ABC, abstractmethod
from stable_baselines3.common.base_class import BaseAlgorithm

class MantisDRLAgent(ABC):
    """
    Interfaccia comune per tutti gli agenti DRL nell'ensemble.
    Ispirata al wrapper di FinRL models.py.
    
    Ogni agente DRL wrapper fornisce la stessa interfaccia indipendentemente
    dall'algoritmo sottostante (PPO, SAC, A2C, TD3).
    """
    
    algorithm_name: str           # "PPO" | "SAC" | "A2C" | "TD3"
    best_regime: list[str]        # Regimi in cui questo algoritmo eccelle
    
    def __init__(self, env: gym.Env, config: DRLConfig):
        self._model: Optional[BaseAlgorithm] = None
        self._env = env
        self._config = config
        self._performance_history: list[PerformanceSnapshot] = []
    
    @abstractmethod
    def train(self, total_timesteps: int) -> TrainingResult:
        """Addestra il modello per N timesteps."""
        ...
    
    @abstractmethod
    def predict(self, observation: np.ndarray, 
                deterministic: bool = True) -> tuple[int, dict]:
        """Predice l'azione dato uno stato osservato."""
        ...
    
    def evaluate(self, eval_env: gym.Env, n_eval_episodes: int = 5) -> PerformanceMetrics:
        """
        Valuta il modello su un env di valutazione.
        Calcola: Sharpe, Sortino, Calmar, Max Drawdown, Win Rate, Profit Factor
        """
        ...
    
    def save(self, path: Path):
        """Salva il modello su disco con metadata."""
        ...
    
    @classmethod
    def load(cls, path: Path, env: gym.Env) -> "MantisDRLAgent":
        """Carica modello da disco."""
        ...
    
    def get_recent_performance(self, window_hours: float = 24) -> PerformanceMetrics:
        """Performance nelle ultime N ore — usato dall'ensemble per routing."""
        ...
```

### Task 5.2 — I 4 Agenti Specializzati
Crea un file per ogni algoritmo in `mantis/drl/agents/`:

**`mantis/drl/agents/ppo_agent.py`** — PPO (Proximal Policy Optimization)
```python
class PPOAgent(MantisDRLAgent):
    """
    PPO: best per mercati trending con oscillazioni moderate.
    Stabile, sample-efficient, buon default.
    Regime ottimale: TRENDING_UP, TRENDING_DOWN
    """
    algorithm_name = "PPO"
    best_regime = ["TRENDING_UP", "TRENDING_DOWN"]
    
    DEFAULT_CONFIG = {
        "policy": "MlpPolicy",
        "learning_rate": 3e-4,
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "ent_coef": 0.01,  # leggera esplorazione
    }
```

**`mantis/drl/agents/sac_agent.py`** — SAC (Soft Actor-Critic)
```python
class SACAgent(MantisDRLAgent):
    """
    SAC: best per mercati ranging con alta volatilità.
    Off-policy, massimizza entropia — più esplorativo.
    Regime ottimale: RANGING, HIGH_VOLATILITY
    """
    algorithm_name = "SAC"
    best_regime = ["RANGING", "HIGH_VOLATILITY"]
    
    DEFAULT_CONFIG = {
        "policy": "MlpPolicy",
        "learning_rate": 3e-4,
        "buffer_size": 100_000,
        "batch_size": 256,
        "tau": 0.005,
        "gamma": 0.99,
        "ent_coef": "auto",  # SAC adatta automaticamente l'entropia
    }
```

**`mantis/drl/agents/a2c_agent.py`** — A2C (Advantage Actor-Critic)
```python
class A2CAgent(MantisDRLAgent):
    """
    A2C: fast, buono per training rapido e mercati veloci (scalping).
    On-policy, aggiornamenti frequenti.
    Regime ottimale: BREAKOUT, HIGH_MOMENTUM
    """
    algorithm_name = "A2C"
    best_regime = ["BREAKOUT", "HIGH_MOMENTUM"]
```

**`mantis/drl/agents/td3_agent.py`** — TD3 (Twin Delayed DDPG)
```python
class TD3Agent(MantisDRLAgent):
    """
    TD3: più stabile di DDPG, buono per azioni continue (position sizing).
    Ottimo per ottimizzare la SIZE della posizione.
    Regime ottimale: LOW_VOLATILITY, ACCUMULATION
    """
    algorithm_name = "TD3"
    best_regime = ["LOW_VOLATILITY", "ACCUMULATION"]
```

### Task 5.3 — DRL Ensemble
Crea `mantis/drl/ensemble.py`:

```python
class MantisDRLEnsemble:
    """
    Ensemble di 4 agenti DRL con routing dinamico basato sul regime.
    Ispirato alla logica di FinRL di confrontare più agenti su stessi dati.
    
    Modalità di voting:
    1. REGIME_ROUTING: usa l'agente migliore per il regime corrente
    2. WEIGHTED_VOTE: voto pesato per performance recente di tutti gli agenti
    3. CONFIDENCE_GATE: usa ensemble solo se confidence >= soglia, altrimenti HOLD
    
    Il risultato dell'ensemble è un DRLEnsembleSignal che entra
    nel MantisAgentOrchestrator come agente "DRL_ENSEMBLE".
    """
    
    agents: dict[str, MantisDRLAgent]  # {"PPO": PPOAgent, "SAC": SACAgent, ...}
    voting_mode: Literal["REGIME_ROUTING", "WEIGHTED_VOTE", "CONFIDENCE_GATE"]
    
    def predict(self, observation: np.ndarray, 
                current_regime: str) -> DRLEnsembleSignal:
        """
        Produce il segnale ensemble.
        
        In REGIME_ROUTING:
        - Identifica agenti con `current_regime` in `best_regime`
        - Se più agenti matchano, usa il weighted vote tra di essi
        - Se nessuno matcha, usa WEIGHTED_VOTE su tutti
        
        In WEIGHTED_VOTE:
        - Ogni agente vota con peso = sharpe_recente / sum(sharpe_tutti)
        - Azione con più peso vince
        
        Output:
        - action: azione finale
        - confidence: agreement score (1.0 = tutti d'accordo)
        - contributing_agents: chi ha influenzato la decisione
        - regime_match: se il regime corrisponde al best_regime di almeno un agente
        """
        ...
    
    def get_ensemble_performance(self) -> EnsemblePerformance:
        """Performance comparativa di tutti gli agenti."""
        ...
    
    def _weight_by_recent_performance(self) -> dict[str, float]:
        """Calcola pesi in base a Sharpe ratio delle ultime 24h."""
        ...
```

### Task 5.4 — Training Pipeline
Crea `mantis/drl/trainer.py`:

```python
class MantisDRLTrainer:
    """
    Pipeline train-test-trade ispirata a FinRL.
    
    Workflow:
    1. TRAIN: addestra tutti e 4 gli agenti su dati storici (80%)
    2. TEST: valuta su OOS data (20%)
    3. COMPARE: confronta metriche, seleziona top performer per regime
    4. DEPLOY: carica i modelli nell'ensemble per live trading
    
    Aggiornamento periodico: ogni settimana, re-addestra su finestra mobile.
    """
    
    def train_all_agents(self, 
                         train_df: pl.DataFrame,
                         total_timesteps: int = 50_000) -> dict[str, TrainingResult]:
        """
        Addestra tutti e 4 gli agenti in parallelo (multiprocessing).
        Ispirato a FinRL: usa lo stesso env per tutti gli agenti per confronto fair.
        """
        ...
    
    def evaluate_and_compare(self, 
                              test_df: pl.DataFrame) -> ComparisonReport:
        """
        Valuta tutti gli agenti su OOS data.
        Produce report comparativo con:
        - Sharpe Ratio per agente
        - Max Drawdown per agente  
        - Calmar Ratio per agente
        - Win Rate per agente
        - Regime breakdown: performance per tipo di mercato
        
        Ispirato a FinRL: plot del cumulative return di tutti gli agenti.
        """
        ...
    
    def auto_select_for_regimes(self, 
                                 comparison: ComparisonReport) -> RegimeAgentMap:
        """
        Dopo il confronto, mappa automaticamente agente migliore per regime.
        Override del default `best_regime` se i dati empirici dicono diversamente.
        """
        ...
```

### Task 5.5 — Performance Analyzer
Crea `mantis/drl/performance_analyzer.py`:

Ispirato a `FinRL-Trading/src/trading/performance_analyzer.py`:

```python
class MantisPerformanceAnalyzer:
    """Calcola metriche di performance professionale per gli agenti DRL."""
    
    def sharpe_ratio(self, returns: np.ndarray, 
                     risk_free_rate: float = 0.02) -> float: ...
    
    def sortino_ratio(self, returns: np.ndarray,
                      risk_free_rate: float = 0.02) -> float: ...
    
    def calmar_ratio(self, returns: np.ndarray, 
                     period_years: float = 1.0) -> float: ...
    
    def max_drawdown(self, equity_curve: np.ndarray) -> float: ...
    
    def profit_factor(self, trades: list[TradeOutcome]) -> float: ...
    
    def win_rate(self, trades: list[TradeOutcome]) -> float: ...
    
    def generate_report(self, equity_curve: np.ndarray,
                        trades: list[TradeOutcome]) -> PerformanceReport:
        """Report completo con tutte le metriche."""
        ...
```

### Task 5.6 — DRL Ensemble Agent per Sprint 1
Crea `mantis/drl/drl_ensemble_agent.py`:

```python
class MantisDRLEnsembleAgent(MantisBaseAgent):
    """
    Integra il DRL Ensemble nel MantisAgentOrchestrator (Sprint 1).
    Ruolo: "DRL_ENSEMBLE"
    Peso nel FinalDecision: configurabile (default 0.25)
    
    Attiva solo quando confidence >= config.drl_confidence_threshold (default 0.6)
    Altrimenti contribuisce con "HOLD" nel voto dell'orchestrator.
    """
    
    def analyze(self, market_context: MarketContext) -> DRLSignal:
        obs = self._build_observation(market_context)
        regime = self._detect_regime(market_context)
        ensemble_signal = self._ensemble.predict(obs, regime)
        
        return DRLSignal(
            action=ensemble_signal.action,
            confidence=ensemble_signal.confidence,
            contributing_agents=ensemble_signal.contributing_agents,
            regime_match=ensemble_signal.regime_match
        )
```

### Task 5.7 — Backtesting Integration
Crea `mantis/drl/backtest.py`:

```python
class MantisDRLBacktester:
    """
    Backtester per validare l'ensemble prima del deploy live.
    Usa dati storici BTC/USDT.
    
    Produce report con:
    - Equity curve completa
    - Trade-by-trade log
    - Confronto con benchmark (Buy & Hold BTC)
    - Metriche di performance da PerformanceAnalyzer
    - Heatmap performance per ora del giorno (utile per scalping BTC)
    """
    
    def run(self, historical_df: pl.DataFrame,
            config: BacktestConfig) -> BacktestResult:
        ...
    
    def plot_results(self, result: BacktestResult) -> bytes:
        """Genera PNG con equity curve e metriche. Usabile nel dashboard Angular."""
        ...
```

---

## 🧪 TEST RICHIESTI

Crea `tests/test_drl.py`:
- Test che tutti e 4 gli agenti condividono la stessa interfaccia
- Test training smoke: 1000 steps su dati fixture senza errori
- Test ensemble voting con mock agents (tutti d'accordo → confidence 1.0)
- Test regime routing (RANGING → seleziona SAC)
- Test performance metrics su trades fixture noti
- Test backtester produce BacktestResult con tutte le metriche

---

## 📊 CONFIG YAML TARGET

```yaml
drl:
  enabled: true
  algorithms: ["PPO", "SAC", "A2C", "TD3"]
  voting_mode: "REGIME_ROUTING"  # REGIME_ROUTING | WEIGHTED_VOTE | CONFIDENCE_GATE
  confidence_threshold: 0.6      # Soglia minima per agire
  ensemble_weight: 0.25          # Peso nel FinalDecision orchestrator
  training:
    total_timesteps: 50000
    retrain_interval_days: 7
    train_test_split: 0.8
    sliding_window_candles: 2000
  performance:
    min_sharpe_for_deploy: 0.5
    max_drawdown_for_deploy: 0.15
```

---

## ✅ CRITERI DI COMPLETAMENTO SPRINT 5

- [ ] `mantis/drl/` package con tutti i file richiesti
- [ ] 4 agenti DRL implementati con interfaccia comune
- [ ] `MantisDRLEnsemble` produce segnali con confidence score
- [ ] `MantisDRLTrainer` pipeline train-test-compare funzionante
- [ ] `PerformanceAnalyzer` calcola correttamente Sharpe, Sortino, Calmar
- [ ] `MantisDRLEnsembleAgent` integrato nell'Orchestrator (Sprint 1)
- [ ] Backtester produce BacktestResult completo
- [ ] Test passano
- [ ] `requirements_evolution.txt`: `stable-baselines3[extra]` (per TD3)

---

*Sprint 5 di 5 | Dipende da: Sprint 1, Sprint 2 | Blocca: nessuno*
