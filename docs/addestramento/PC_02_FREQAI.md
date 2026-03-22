# MANTIS AI — PROMPT CONTRACT 02
## Sprint: Reinforcement Learning & Adaptive Retraining
## Sorgente: `freqtrade/freqtrade` (modulo FreqAI)

---

## 🎯 OBIETTIVO SPRINT

Dotare MANTIS di un layer di **Reinforcement Learning** che si affianca all'XGBoost esistente,
aggiungendo un agente RL che si auto-adatta alle condizioni di mercato in tempo reale.
Il cuore è una `calculate_reward()` function customizzata per il profilo di trading
scalping/swing su BTC/USDT di MANTIS.

**Non si tratta di sostituire XGBoost** — il sistema finale usa un ensemble
XGBoost (predizione) + RL (adattamento dinamico).

---

## 📂 NAVIGAZIONE REPO SORGENTE

```bash
gh repo clone freqtrade/freqtrade /tmp/source_repos/freqtrade/
```

### File chiave da analizzare (in ordine):
```
freqtrade/
├── freqtrade/freqai/
│   ├── base_models/
│   │   └── BaseReinforcementLearner.py   ← PRIORITÀ 1: struttura base RL
│   ├── prediction_models/
│   │   └── ReinforcementLearner.py       ← PRIORITÀ 1: implementazione concreta
│   ├── RL/
│   │   ├── Base5ActionRLEnv.py           ← PRIORITÀ 1: ambiente gym (5 azioni)
│   │   └── BaseEnvironment.py            ← PRIORITÀ 1: env base con state info
│   ├── data_kitchen.py                   ← PRIORITÀ 2: feature engineering pipeline
│   └── feature_engineering.py           ← PRIORITÀ 2: come aggiungono features
├── freqtrade/templates/
│   └── FreqaiExampleStrategy.py          ← PRIORITÀ 2: esempio completo integrato
└── docs/freqai-reinforcement-learning.md ← PRIORITÀ 1: documentazione reward
```

### Cosa estrarre:
1. **Struttura dell'ambiente Gym** con 5 azioni (Long entry/exit, Short entry/exit, Neutral)
2. **State information pattern**: profit corrente, posizione, durata trade
3. **`calculate_reward()` design pattern** con esempi concreti
4. **Pipeline di retraining automatico** in background thread
5. **Feature engineering** per creare "feature sets" da indicatori base

---

## 🏗️ TASK DI IMPLEMENTAZIONE

### Task 2.1 — Ambiente RL Custom per MANTIS
Crea `mantis/rl/environment.py`:

```python
import gymnasium as gym
from stable_baselines3.common.env_checker import check_env

class MantisRLEnvironment(gym.Env):
    """
    Ambiente RL per MANTIS, ispirato a FreqAI BaseEnvironment.
    
    Azioni: 5 discrete
      0: Long Entry
      1: Long Exit  
      2: Short Entry
      3: Short Exit
      4: Neutral (Hold)
    
    State: [features_vector, current_profit, position, trade_duration, volatility_regime]
    
    Reward: calcolata da MantisRewardCalculator (vedi Task 2.2)
    """
    
    # Da FreqAI: usa features già calcolate, non ricalcola
    def __init__(self, features_df: pl.DataFrame, config: RLConfig):
        ...
    
    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        # Avanza di un candle, applica azione, calcola reward
        ...
    
    def reset(self, seed=None) -> tuple[np.ndarray, dict]:
        # Reset ambiente a inizio episodio
        ...
    
    def _get_state(self) -> np.ndarray:
        """
        CRITICO: include state information come FreqAI
        - Feature vector dal candle corrente
        - current_profit: P&L trade aperto (0 se nessuno)
        - position: -1 (short) / 0 (flat) / 1 (long)
        - trade_duration: candles da apertura trade (0 se flat)
        - volatility_regime: 0-3 (LOW/MED/HIGH/EXTREME) da VPIN
        """
        ...
```

**Vincoli:**
- Usa `polars` per manipolazione dati (già nel progetto)
- Compatibile con `stable_baselines3` (aggiungi a `requirements_evolution.txt`)
- Passa `check_env(env)` di stable_baselines3 senza errori

### Task 2.2 — Reward Calculator
Crea `mantis/rl/reward_functions.py`:

Questo è il file più critico dello sprint. Implementa almeno 3 reward functions:

```python
class MantisRewardCalculator:
    
    def sharpe_reward(self, env_state: EnvState) -> float:
        """
        Reward basata su Sharpe ratio incrementale.
        Penalizza trades con alta volatilità di P&L.
        Ispirata a FreqAI SharpeRatioReward.
        """
        ...
    
    def scalping_reward(self, env_state: EnvState) -> float:
        """
        Reward ottimizzata per scalping BTC/USDT:
        + Premio per profitti rapidi (< 10 candle)
        + Premio per win rate elevato
        - Penalità forte per drawdown > 1%
        - Penalità per overtrading (> N trades per sessione)
        - Penalità per tenere posizioni in regime HIGH/EXTREME volatility
        Questa è la reward function principale di MANTIS.
        """
        ...
    
    def risk_adjusted_reward(self, env_state: EnvState) -> float:
        """
        Reward con Kelly Criterion integrato:
        Scala il reward in base all'edge stimato e alla bankroll.
        Usa i parametri Kelly già calcolati da MANTIS.
        """
        ...
    
    def composite_reward(self, env_state: EnvState, 
                         weights: dict = None) -> float:
        """
        Weighted combination delle 3 reward functions.
        Default: 0.4 scalping + 0.4 sharpe + 0.2 risk_adjusted
        Weights configurabili da config.yaml
        """
        ...
```

**Parametri chiave da esporre in config:**
```yaml
rl:
  reward_function: "composite"  # scalping | sharpe | risk_adjusted | composite
  reward_weights:
    scalping: 0.4
    sharpe: 0.4
    risk_adjusted: 0.2
  max_trades_per_session: 20
  target_hold_candles: 10
  max_drawdown_pct: 0.01
```

### Task 2.3 — Adaptive Trainer
Crea `mantis/rl/adaptive_trainer.py`:

```python
class MantisAdaptiveTrainer:
    """
    Ispirato al FreqAI background retraining thread.
    
    Esegue retraining del modello RL in background mentre MANTIS opera live.
    Usa una sliding window di dati recenti per adattarsi al mercato attuale.
    
    NON blocca il thread principale di trading.
    """
    
    # Pattern chiave da FreqAI:
    # - training su thread separato
    # - sliding window (configurable, default 500 candle)
    # - model versioning: mantieni ultimi N modelli per rollback
    # - hot-swap: nuovo modello entra in produzione senza restart
    
    def __init__(self, config: RLConfig, model_dir: Path):
        self.sliding_window_size = config.sliding_window_size  # default: 500
        self.retrain_interval_minutes = config.retrain_interval  # default: 60
        self._training_thread: Optional[threading.Thread] = None
        self._current_model: Optional[BaseAlgorithm] = None
        self._model_lock = threading.RLock()
    
    def start_background_training(self):
        """Avvia il loop di retraining in background."""
        ...
    
    def get_current_model(self) -> BaseAlgorithm:
        """Thread-safe access al modello corrente."""
        with self._model_lock:
            return self._current_model
    
    def _retrain_loop(self):
        """
        Loop principale di retraining.
        Ogni `retrain_interval_minutes`:
        1. Fetcha dati recenti (sliding window)
        2. Crea nuovo env con dati freschi
        3. Addestra nuovo modello (PPO o SAC)
        4. Valida su validation set
        5. Se performance >= soglia → hot-swap
        6. Salva modello con timestamp per audit
        """
        ...
```

### Task 2.4 — RL Agent Wrapper
Crea `mantis/rl/rl_agent.py`:

Wrapper che integra il modello RL nel sistema degli agenti di Sprint 1:

```python
class MantisRLAgent(MantisBaseAgent):
    """
    Agente RL che si integra nel MantisAgentOrchestrator (Sprint 1).
    Usa il modello addestrato dall'AdaptiveTrainer per produrre
    un RLSignal che viene combinato con i segnali degli altri agenti.
    
    Ruolo nell'orchestrator: "ADAPTIVE_SIGNAL"
    Peso nel FinalDecision: configurabile (default 0.3)
    """
    
    def analyze(self, market_context: MarketContext) -> RLSignal:
        model = self._trainer.get_current_model()
        obs = self._build_observation(market_context)
        action, _states = model.predict(obs, deterministic=True)
        return RLSignal(
            action=self._map_action(action),
            confidence=self._estimate_confidence(_states),
            model_version=self._trainer.current_model_version
        )
```

### Task 2.5 — Feature Engineering Pipeline
Crea `mantis/rl/feature_pipeline.py`:

Ispirato a FreqAI `data_kitchen.py`:
- Normalizzazione features (z-score rolling su 200 candle)
- Lag features automatiche (t-1, t-2, t-3 per le top 20 features per importance)
- Feature per il contesto dell'ambiente RL (non per XGBoost)
- Denota le features RL con prefisso `rl_` per distinguerle

---

## ⚙️ ALGORITMO RL DA USARE

Implementa supporto per 2 algoritmi (configurabile):

```python
# Algoritmo primario per scalping (bassa latenza di inferencing)
PPO_CONFIG = {
    "policy": "MlpPolicy",
    "learning_rate": 3e-4,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,  # discount factor
}

# Algoritmo secondario per position holding più lungo
SAC_CONFIG = {
    "policy": "MlpPolicy", 
    "learning_rate": 3e-4,
    "buffer_size": 100_000,
    "tau": 0.005,
}
```

---

## 🧪 TEST RICHIESTI

Crea `tests/test_rl.py`:
- Test che `MantisRLEnvironment` passa `check_env()`
- Test che `scalping_reward` penalizza correttamente drawdown > 1%
- Test che `AdaptiveTrainer` non blocca il thread principale (async test)
- Test smoke: addestra PPO per 1000 steps su dati fixture, verifica converge

---

## ✅ CRITERI DI COMPLETAMENTO SPRINT 2

- [ ] `mantis/rl/` package con tutti i file richiesti
- [ ] `MantisRLEnvironment` passa `check_env()`
- [ ] Almeno 3 reward functions implementate
- [ ] `AdaptiveTrainer` gira in background thread senza bloccare
- [ ] `MantisRLAgent` si integra con `MantisAgentOrchestrator`
- [ ] Config YAML aggiornata con sezione `rl:`
- [ ] Test passano
- [ ] `requirements_evolution.txt` aggiornato: `stable-baselines3`, `gymnasium`

---

*Sprint 2 di 5 | Dipende da: Sprint 1 (MantisBaseAgent) | Blocca: Sprint 5*
