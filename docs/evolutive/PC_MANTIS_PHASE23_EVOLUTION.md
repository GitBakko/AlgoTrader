# MANTIS AI — PROMPT CONTRACT
## Phase 23: Resilience-First Evolution
## Target: BTC/USDT Perpetual Futures — Bybit
## Repository: github.com/GitBakko/AlgoTrader

---

## 📋 INDICE

1. [Contesto e Stato Attuale](#1-contesto-e-stato-attuale)
2. [Diagnosi Critica](#2-diagnosi-critica)
3. [Piano di Implementazione — 6 Sprint](#3-piano-di-implementazione)
4. [Sprint 1 — Regime-Gated Execution](#sprint-1--regime-gated-execution)
5. [Sprint 2 — Funding Rate Engine](#sprint-2--funding-rate-engine)
6. [Sprint 3 — Walk-Forward Validation Framework](#sprint-3--walk-forward-validation-framework)
7. [Sprint 4 — RL Adattivo con Reward Custom](#sprint-4--rl-adattivo-con-reward-custom)
8. [Sprint 5 — Liquidations Heatmap Integration](#sprint-5--liquidations-heatmap-integration)
9. [Sprint 6 — Multi-Agent Debate Layer](#sprint-6--multi-agent-debate-layer)
10. [Regole Globali e Anti-Pattern](#10-regole-globali-e-anti-pattern)
11. [Criteri di Completamento Globali](#11-criteri-di-completamento-globali)

---

## 1. Contesto e Stato Attuale

### Stack MANTIS Phase 22 — NON modificare senza migration script

```
Backend:      Python / FastAPI
Frontend:     Angular
Data layer:   Polars
ML Core:      XGBoost classifier
Broker:       Bybit (BTC/USDT perpetual futures)
Features:     220+ (OFI, VPIN, Hawkes Processes, COT proxy,
              Fear & Greed, FRED, Alpha Vantage, StockTwits, Finnhub)
Target:       Scalping + swing su BTC/USDT perpetual
Repo:         github.com/GitBakko/AlgoTrader
```

### Architettura esistente — contratti da preservare

- `generate_signal()` → entry point principale del sistema di segnali
- Pipeline XGBoost esistente → non riscrivere, estendere con wrapper
- Feature engineering pipeline Polars → non cambiare schema, aggiungere colonne
- FastAPI endpoints esistenti → aggiungere nuovi, non modificare quelli live
- Tutto il codice nuovo va taggato con `# MANTIS-P23:` nei commenti

---

## 2. Diagnosi Critica

### Il problema strutturale

XGBoost è un classificatore **statico** addestrato su una distribuzione storica.
BTC/USDT perpetual è uno dei mercati più **non-stazionari** al mondo:
il regime cambia ogni 6-72 ore (trend, mean-reversion, volatility crush, liquidity hunt).

Il modello continua a emettere previsioni anche quando il mercato ha cambiato struttura
rispetto alla distribuzione di training. Questo genera la maggioranza dei drawdown.

### Gerarchia delle priorità (ROI decrescente)

```
1. Regime-Gated Execution     → impatto immediato, complessità bassa
2. Funding Rate Engine        → alpha puro, gratuito, sottoutilizzato
3. Walk-Forward Validation    → diagnostico, obbligatorio prima dell'RL
4. RL Adattivo                → impatto alto, complessità alta
5. Liquidations Heatmap       → alpha strutturale su BTC specificamente
6. Multi-Agent Debate         → raffinamento qualitativo
```

> ⚠️ **Regola fondamentale**: completare ogni sprint in ordine.
> Non iniziare Sprint 4 (RL) senza avere i risultati del Sprint 3 (Walk-Forward).
> Un RL sopra un modello non validato produce un sistema più sofisticato che perde con più eleganza.

---

## 3. Piano di Implementazione

### Mappa sprint e dipendenze

```
Sprint 1 (Regime Gate)
    └─► Sprint 2 (Funding Rate)
            └─► Sprint 3 (Walk-Forward Validation)  ← GATE OBBLIGATORIO
                    └─► Sprint 4 (RL Adattivo)
                            └─► Sprint 5 (Liquidations Heatmap)
                                    └─► Sprint 6 (Multi-Agent Debate)
```

### Stima impatto per sprint

| Sprint | Complessità | Impatto P&L stimato | Impatto Resilienza |
|--------|-------------|---------------------|--------------------|
| 1 — Regime Gate | Bassa | +15–25% net P&L | ⭐⭐⭐⭐⭐ |
| 2 — Funding Rate | Bassa | +8–15% | ⭐⭐⭐⭐ |
| 3 — Walk-Forward | Media | Diagnostico | ⭐⭐⭐⭐⭐ |
| 4 — RL Adattivo | Alta | +10–20% | ⭐⭐⭐⭐ |
| 5 — Liquidations | Media | +10–18% | ⭐⭐⭐ |
| 6 — Multi-Agent | Alta | +5–10% | ⭐⭐⭐ |

---

## Sprint 1 — Regime-Gated Execution

### Obiettivo

Implementare un gate che blocca l'esecuzione del segnale quando il regime di mercato
non è riconoscibile dal modello con sufficiente confidenza.

**Principio**: il 60–70% dei drawdown nei sistemi algo avviene in regimi non mappati.
Stare fermi è una posizione di trading attiva e profittevole.

### Task 1.1 — HMM Regime Detector

Crea `mantis/regime/hmm_detector.py`:

```python
# MANTIS-P23: HMM Regime Detector
# Rileva il regime corrente e la sua probabilità via Hidden Markov Model

from hmmlearn import hmm
import polars as pl
import numpy as np
from dataclasses import dataclass
from enum import IntEnum

class MarketRegime(IntEnum):
    TRENDING_UP = 0
    TRENDING_DOWN = 1
    MEAN_REVERTING = 2
    HIGH_VOLATILITY = 3
    UNKNOWN = 4  # ← questo è il regime che blocca l'esecuzione

@dataclass
class RegimeState:
    regime: MarketRegime
    confidence: float          # 0.0 → 1.0, probabilità del regime corrente
    regime_duration: int       # candle dall'ultimo cambio regime
    is_tradeable: bool         # False se confidence < threshold

class MantisHMMDetector:
    """
    HMM a 4 stati addestrato su features di volatilità e trend.
    Input: DataFrame Polars con colonne [returns, realized_vol, volume_ratio]
    Output: RegimeState
    """
    
    CONFIDENCE_THRESHOLD = 0.65  # Sotto questa soglia → NO_TRADE
    
    def __init__(self, n_components: int = 4):
        self.model = hmm.GaussianHMM(
            n_components=n_components,
            covariance_type="full",
            n_iter=1000,
            random_state=42
        )
        self.is_fitted = False
    
    def fit(self, features_df: pl.DataFrame) -> None:
        """
        Addestra HMM su dati storici.
        Da chiamare in fase di training, non in live.
        """
        ...
    
    def predict_regime(self, recent_df: pl.DataFrame) -> RegimeState:
        """
        Predice il regime corrente con confidence score.
        Imposta is_tradeable=False se confidence < CONFIDENCE_THRESHOLD.
        """
        ...
    
    def get_regime_history(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Aggiunge colonne 'regime' e 'regime_confidence' al DataFrame.
        Usato per feature engineering e analisi storica.
        """
        ...
```

**Dipendenze da aggiungere a requirements.txt:**
```
hmmlearn>=0.3.0
```

### Task 1.2 — Feature Distribution Drift Monitor

Crea `mantis/regime/drift_monitor.py`:

```python
# MANTIS-P23: Feature Distribution Drift Monitor
# Rileva quando le feature live si sono allontanate dalla distribuzione di training

from scipy import stats
import polars as pl
import numpy as np
from dataclasses import dataclass

@dataclass
class DriftReport:
    overall_drift_score: float    # 0.0 (no drift) → 1.0 (massimo drift)
    drifted_features: list[str]   # feature con PSI > threshold
    is_safe: bool                  # False se drift_score > 0.3

class MantisDriftMonitor:
    """
    Usa Population Stability Index (PSI) per monitorare drift delle feature.
    PSI < 0.1  → stabile
    PSI 0.1-0.2 → monitorare
    PSI > 0.2  → drift significativo → blocca esecuzione
    """
    
    PSI_THRESHOLD = 0.2
    TOP_FEATURES_TO_MONITOR = 30  # monitora le 30 feature più importanti per XGBoost
    
    def __init__(self):
        self.training_distributions: dict = {}
    
    def fit_training_distributions(self, training_df: pl.DataFrame) -> None:
        """
        Salva le distribuzioni delle feature di training come reference.
        Da chiamare una volta dopo ogni retraining del modello XGBoost.
        Persiste su disco: mantis/regime/training_distributions.pkl
        """
        ...
    
    def compute_psi(self, feature_name: str, live_series: pl.Series) -> float:
        """
        Calcola PSI tra distribuzione di training e valori live recenti.
        """
        ...
    
    def check_drift(self, live_df: pl.DataFrame, window: int = 100) -> DriftReport:
        """
        Controlla drift su finestra di 'window' candle recenti.
        Ritorna DriftReport con is_safe=False se drift eccessivo.
        """
        ...
```

### Task 1.3 — Regime Gate — integrazione nel segnale

Modifica `generate_signal()` esistente aggiungendo un wrapper, **NON modificare** la funzione originale:

```python
# MANTIS-P23: Regime Gate Wrapper
# Wrappa generate_signal() bloccando l'esecuzione se il regime non è sicuro

from mantis.regime.hmm_detector import MantisHMMDetector, MarketRegime
from mantis.regime.drift_monitor import MantisDriftMonitor
from mantis.signals.base import Signal  # import dal modulo esistente

class RegimeGatedSignalGenerator:
    """
    Wrapper attorno a generate_signal() esistente.
    Aggiunge un layer di validazione regime prima di emettere segnali.
    """
    
    def __init__(self, original_signal_fn, hmm: MantisHMMDetector, drift: MantisDriftMonitor):
        self._generate_signal = original_signal_fn
        self.hmm = hmm
        self.drift = drift
        self.blocked_count = 0  # metrica per monitoring
        self.passed_count = 0
    
    def generate_signal(self, features_df: pl.DataFrame) -> Signal:
        """
        1. Controlla regime HMM → blocca se confidence < 0.65
        2. Controlla drift → blocca se PSI > 0.2
        3. Se entrambi OK → delega a generate_signal() originale
        4. Logga sempre la decisione (anche NO_TRADE) su DB
        """
        regime_state = self.hmm.predict_regime(features_df)
        drift_report = self.drift.check_drift(features_df)
        
        if not regime_state.is_tradeable:
            return Signal.NO_TRADE(reason=f"HMM confidence {regime_state.confidence:.2f} < 0.65")
        
        if not drift_report.is_safe:
            return Signal.NO_TRADE(reason=f"Drift score {drift_report.overall_drift_score:.2f}")
        
        return self._generate_signal(features_df)
```

### Task 1.4 — Regime Dashboard

Aggiungi endpoint FastAPI `GET /api/regime/status`:

```python
# MANTIS-P23: Regime Status Endpoint
@router.get("/api/regime/status")
async def get_regime_status() -> RegimeStatusResponse:
    """
    Ritorna lo stato corrente del regime detector.
    Usato dal frontend Angular per mostrare il "semaforo" di trading.
    
    Response:
    {
        "regime": "TRENDING_UP",
        "confidence": 0.82,
        "is_tradeable": true,
        "drift_score": 0.08,
        "blocked_last_hour": 3,
        "passed_last_hour": 12
    }
    """
```

### Criteri di completamento Sprint 1

- [ ] `MantisHMMDetector` addestrato e validato su dati storici BTC 2022-2024
- [ ] `MantisDriftMonitor` calibrato sulle 30 feature più importanti per XGBoost
- [ ] `RegimeGatedSignalGenerator` wrappa correttamente `generate_signal()` senza modificarla
- [ ] Endpoint `/api/regime/status` funzionante
- [ ] Test unitari per tutti i componenti
- [ ] Backtesting comparativo: P&L con gate vs P&L senza gate su dati 2024
- [ ] `MIGRATION_NOTE.md` che documenta l'integrazione nel sistema esistente

---

## Sprint 2 — Funding Rate Engine

### Obiettivo

Costruire un motore di analisi del funding rate che trasformi questo dato grezzo
in feature di alta qualità per il modello XGBoost e in segnali contrarian diretti.

### Contesto: perché il funding rate è cruciale

Il funding rate BTC perpetual è il sostituto del COT data per il crypto:
misura il costo del carry per i long vs short e riflette il posizionamento del mercato.

Pattern ad alta affidabilità:
- **Funding estremo positivo** (> +0.1%) → mercato eccessivamente long → contrarian short
- **Funding estremo negativo** (< -0.05%) → mercato eccessivamente short → contrarian long
- **Funding divergence** → prezzo sale ma funding scende → distribuzione istituzionale
- **Cumulative funding** → costo accumulato che comprime i rendimenti dei long

### Task 2.1 — Bybit Funding Rate Fetcher

Crea `mantis/data/funding_rate_fetcher.py`:

```python
# MANTIS-P23: Funding Rate Fetcher — Bybit API
# Fetch funding rate storico e real-time per BTC/USDT perpetual

import httpx
import polars as pl
from datetime import datetime, timedelta

class BybitFundingRateFetcher:
    """
    Fetcha funding rate da Bybit:
    - Endpoint storico: GET /v5/market/funding/history
    - Refresh: ogni 8 ore (funding si aggiorna a 00:00, 08:00, 16:00 UTC)
    
    Simbolo: BTCUSDT
    Categoria: linear
    """
    
    BASE_URL = "https://api.bybit.com"
    SYMBOL = "BTCUSDT"
    
    async def fetch_historical(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> pl.DataFrame:
        """
        Ritorna DataFrame con colonne:
        [timestamp, funding_rate, funding_rate_timestamp, predicted_funding_rate]
        """
        ...
    
    async def fetch_latest(self) -> dict:
        """
        Fetch funding rate corrente e predicted (prossima sessione).
        """
        ...
    
    async def fetch_open_interest(self) -> pl.DataFrame:
        """
        Fetch open interest aggregato — dato complementare al funding rate.
        Endpoint: GET /v5/market/open-interest
        """
        ...
```

### Task 2.2 — Funding Rate Feature Engineering

Crea `mantis/features/funding_features.py`:

```python
# MANTIS-P23: Funding Rate Feature Engineering
# Trasforma funding rate grezzo in feature per XGBoost

import polars as pl
import numpy as np

class FundingRateFeatureBuilder:
    """
    Genera le seguenti feature da aggiungere al DataFrame principale:
    
    Feature dirette:
    - funding_rate_current          : valore funding corrente
    - funding_rate_predicted        : valore funding prossima sessione
    - funding_rate_8h_zscore        : z-score su finestra 90 giorni
    - funding_rate_is_extreme_pos   : bool, > +0.10%
    - funding_rate_is_extreme_neg   : bool, < -0.05%
    
    Feature di trend:
    - funding_rate_7d_cumulative    : somma funding ultimi 7 giorni
    - funding_rate_30d_cumulative   : somma funding ultimi 30 giorni
    - funding_rate_momentum_3d      : variazione media vs 3 giorni prima
    - funding_rate_trend            : direzione trend (-1, 0, +1)
    
    Feature di divergenza (richiede prezzo):
    - funding_price_divergence      : correlazione rolling 24h funding vs prezzo
                                      valore negativo = distribuzione istituzionale
    - funding_oi_ratio              : funding / open_interest normalized
    
    Segnali contrarian diretti (non per XGBoost, per gate diretto):
    - funding_contrarian_signal     : +1 (long), -1 (short), 0 (neutro)
    - funding_contrarian_confidence : 0.0 → 1.0
    """
    
    def build_features(
        self, 
        main_df: pl.DataFrame,
        funding_df: pl.DataFrame,
        oi_df: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Join e calcola tutte le feature.
        Ritorna main_df con le nuove colonne aggiunte.
        NON modifica le colonne esistenti.
        """
        ...
    
    def _compute_zscore(self, series: pl.Series, window: int = 1080) -> pl.Series:
        """Z-score rolling su 1080 periodi (90 giorni a 2h candle)"""
        ...
    
    def _detect_divergence(
        self, 
        price: pl.Series, 
        funding: pl.Series, 
        window: int = 12  # 12 candle = 24h su 2h timeframe
    ) -> pl.Series:
        """
        Correlazione rolling prezzo-funding.
        Valori negativi indicano divergenza (distribuzione).
        """
        ...
```

### Task 2.3 — Aggiornamento pipeline feature esistente

Modifica il modulo di feature engineering esistente per includere le funding features:

```python
# MANTIS-P23: Integrazione funding features nella pipeline principale
# Aggiungere chiamata a FundingRateFeatureBuilder nella pipeline esistente
# ATTENZIONE: aggiungere in append, NON modificare le 220 feature esistenti

# Pattern di integrazione:
features_df = existing_feature_pipeline(raw_data)
features_df = funding_builder.build_features(features_df, funding_df, oi_df)
# Il modello XGBoost riceverà le nuove colonne automaticamente
# se le feature sono state aggiunte al training set e il modello è stato ri-addestrato
```

### Task 2.4 — Contrarian Signal Gate

Aggiungere nel `RegimeGatedSignalGenerator` (Sprint 1) un check specifico per funding extremes:

```python
# MANTIS-P23: Funding Contrarian Check
# Se funding è estremo, sovrascrive il segnale XGBoost con contrarian
# Questo è l'unico caso in cui un segnale esterno può sovrascrivere il modello

def _check_funding_override(self, funding_features: dict) -> Signal | None:
    """
    Ritorna segnale contrarian se funding è in zona estrema.
    Ritorna None se il funding è nella norma (lascia decidere a XGBoost).
    
    Logica:
    - funding_zscore > 2.5 → SHORT contrarian (mercato troppo long)
    - funding_zscore < -2.0 → LONG contrarian (mercato troppo short)
    - funding_7d_cumulative > 0.5% → compressione carry, favorisce short
    """
    ...
```

### Criteri di completamento Sprint 2

- [ ] `BybitFundingRateFetcher` con dati storici dal 2021 scaricati e salvati
- [ ] Tutte le 14 funding feature implementate e validate
- [ ] Feature aggiunte al training set XGBoost e modello ri-addestrato
- [ ] Backtesting del contrarian signal su funding extremes (2022-2024)
- [ ] Dashboard endpoint `GET /api/funding/status` con stato corrente
- [ ] Copertura test > 80% sui calcoli delle feature

---

## Sprint 3 — Walk-Forward Validation Framework

### Obiettivo

Costruire un framework rigoroso di walk-forward validation per determinare con certezza
se MANTIS è genuinamente profittevole out-of-sample o stiamo osservando overfitting.

**Questo sprint è un gate obbligatorio prima del RL.**
Se i risultati out-of-sample non sono accettabili, lo Sprint 4 viene bloccato e
si rientra in ciclo di miglioramento del modello base.

### Definizione dei dataset — NON deviare da questa suddivisione

```
Training set:   01/01/2022 → 30/06/2023  (18 mesi)
Validation set: 01/07/2023 → 31/12/2023  (6 mesi) — per hyperparameter tuning
Test set:       01/01/2024 → oggi         (vergine — toccare SOLO una volta)

Regola assoluta: il test set non viene visto dal modello né per training né per tuning.
Guardare il test set e poi modificare il modello invalida l'intero esperimento.
```

### Task 3.1 — Walk-Forward Engine

Crea `mantis/validation/walk_forward.py`:

```python
# MANTIS-P23: Walk-Forward Validation Engine

import polars as pl
import numpy as np
from dataclasses import dataclass
from typing import Callable

@dataclass
class WalkForwardResult:
    # Metriche per ogni fold
    fold_returns: list[float]
    fold_sharpe: list[float]
    fold_max_drawdown: list[float]
    fold_win_rate: list[float]
    fold_trade_count: list[int]
    
    # Metriche aggregate
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    avg_win_rate: float
    
    # Stabilità
    return_consistency: float   # % di fold profittevoli
    sharpe_consistency: float   # % di fold con Sharpe > 0.5
    
    # Flag
    passes_gate: bool           # True se metriche accettabili per procedere con RL

class WalkForwardValidator:
    """
    Walk-forward validation con expanding window.
    
    Schema:
    Fold 1: Train [gen22→giu22], Test [lug22→set22]
    Fold 2: Train [gen22→set22], Test [ott22→dic22]
    Fold 3: Train [gen22→dic22], Test [gen23→mar23]
    ... continua con step di 3 mesi fino al validation set
    
    Expanding window (non rolling) per riflettere come il modello viene
    effettivamente ri-addestrato in produzione.
    """
    
    GATE_CRITERIA = {
        "min_annualized_return": 0.20,      # almeno 20% annuo
        "min_sharpe": 0.8,                   # Sharpe minimo accettabile
        "max_drawdown": -0.25,               # drawdown massimo -25%
        "min_return_consistency": 0.65,      # 65% dei fold deve essere profittevole
        "min_win_rate": 0.48,                # win rate minimo
    }
    
    def run(
        self,
        data: pl.DataFrame,
        train_fn: Callable,      # funzione di training del modello
        predict_fn: Callable,    # funzione di predizione
        step_months: int = 3
    ) -> WalkForwardResult:
        ...
    
    def evaluate_gate(self, result: WalkForwardResult) -> tuple[bool, list[str]]:
        """
        Valuta se i risultati soddisfano i criteri per procedere con RL.
        Ritorna (passes, lista_di_motivi_di_fallimento).
        """
        ...
```

### Task 3.2 — Backtesting Engine

Crea `mantis/validation/backtester.py`:

```python
# MANTIS-P23: Backtester con fee realistiche Bybit

@dataclass
class BacktestConfig:
    maker_fee: float = 0.0002    # 0.02% maker fee Bybit
    taker_fee: float = 0.00055   # 0.055% taker fee Bybit
    slippage_bps: float = 2.0    # 2 bps slippage medio su BTC
    initial_capital: float = 10000.0
    max_position_pct: float = 0.10   # max 10% del capitale per trade
    leverage: float = 3.0             # leva conservativa

class MantisBacktester:
    """
    Backtester event-driven con fee realistiche.
    
    Features:
    - Fee maker/taker differenziate per tipo ordine
    - Slippage stocastico basato su volatilità del candle
    - Funding cost applicato ogni 8h sulle posizioni aperte
    - Liquidation check (non superare margine disponibile)
    - Equity curve dettagliata candle-by-candle
    """
    
    def run(self, signals: pl.DataFrame, prices: pl.DataFrame, config: BacktestConfig) -> BacktestResult:
        ...
    
    def compute_metrics(self, equity_curve: pl.Series) -> PerformanceMetrics:
        """
        Calcola: Total Return, CAGR, Sharpe, Sortino, Calmar, 
                 Max Drawdown, Max DD Duration, Win Rate, 
                 Profit Factor, Average Win/Loss ratio
        """
        ...
```

### Task 3.3 — Report di Validazione

Crea `mantis/validation/report_generator.py`:

Genera un report HTML (accessibile via browser) con:
- Equity curve comparativa (training vs validation vs test)
- Distribuzione dei rendimenti per fold
- Heatmap di performance mensile
- Feature importance XGBoost con drift nel tempo
- Tabella criteri gate con pass/fail per ciascuno

Endpoint: `GET /api/validation/report` → redirect al file HTML

### Criterio gate Sprint 3 → Sprint 4

```python
# Solo se questa condizione è vera si procede con il Sprint 4
if walk_forward_result.passes_gate:
    print("GATE PASSED — Procedere con Sprint 4 (RL)")
else:
    print("GATE FAILED — Rientrare in ciclo di improvement del modello base")
    print("Motivi:", gate_failure_reasons)
    # In questo caso: ottimizzare feature engineering, hyperparameter tuning,
    # migliorare regime detection Sprint 1, aggiungere funding Sprint 2
    # e ripetere Sprint 3 prima di procedere
```

### Criteri di completamento Sprint 3

- [ ] Walk-forward engine con expanding window implementato e testato
- [ ] Backtester con fee Bybit realistiche (maker/taker/funding/slippage)
- [ ] Report HTML generato e accessibile da browser
- [ ] Gate criteria definiti e validati sul validation set
- [ ] Test set toccato UNA SOLA VOLTA per la valutazione finale
- [ ] Documento `VALIDATION_REPORT.md` con risultati reali (non simulati)

---

## Sprint 4 — RL Adattivo con Reward Custom

### Prerequisito obbligatorio

**Sprint 3 deve essere completato e il gate deve essere PASSED.**

### Obiettivo

Aggiungere un layer di Reinforcement Learning che si affianca al modello XGBoost esistente,
permettendo al sistema di adattarsi dinamicamente ai cambi di regime senza necessità
di retraining manuale.

L'RL **non sostituisce XGBoost** — opera come ensemble:
- XGBoost → predice direzione (signal)
- RL → ottimizza timing e sizing dell'esecuzione

### Task 4.1 — Ambiente Gym per MANTIS

Crea `mantis/rl/environment.py`:

```python
# MANTIS-P23: Gymnasium Environment per MANTIS RL

import gymnasium as gym
import numpy as np
import polars as pl
from stable_baselines3.common.env_checker import check_env

class MantisRLEnvironment(gym.Env):
    """
    5 azioni discrete:
      0: Long Entry
      1: Long Exit
      2: Short Entry
      3: Short Exit
      4: Neutral / Hold
    
    State vector (da costruire in _get_state):
      - Feature vector XGBoost (top 50 per importanza)
      - current_profit_pct     : P&L trade aperto (0 se flat)
      - position               : -1 (short) / 0 (flat) / 1 (long)
      - trade_duration_candles : candle dall'apertura (0 se flat)
      - hmm_regime             : 0-3 (regime corrente da Sprint 1)
      - hmm_confidence         : 0.0-1.0 (confidence regime)
      - funding_zscore         : z-score funding corrente (da Sprint 2)
      - realized_vol_1h        : volatilità realizzata ultima ora
    """
    
    metadata = {"render_modes": ["human"]}
    
    def __init__(self, features_df: pl.DataFrame, config: dict):
        super().__init__()
        
        # Azioni e osservazioni
        self.action_space = gym.spaces.Discrete(5)
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(50 + 7,),  # top 50 feature + 7 state variables
            dtype=np.float32
        )
        ...
    
    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        """
        Avanza di un candle.
        Applica azione, calcola reward, aggiorna stato.
        """
        ...
    
    def reset(self, seed=None) -> tuple[np.ndarray, dict]:
        ...
    
    def _get_state(self) -> np.ndarray:
        """Costruisce il vettore di stato corrente."""
        ...
```

**Validazione obbligatoria:**
```python
env = MantisRLEnvironment(features_df, config)
check_env(env)  # deve passare senza errori
```

### Task 4.2 — Reward Function MANTIS-Specifica

Crea `mantis/rl/reward_functions.py`:

```python
# MANTIS-P23: Reward Functions ottimizzate per scalping BTC/USDT
# La reward function è il componente più critico dell'intero Sprint 4

import numpy as np
from dataclasses import dataclass

@dataclass
class EnvState:
    profit_pct: float
    trade_duration: int
    daily_trade_count: int
    max_daily_trades: int
    hmm_regime: int
    hmm_confidence: float
    portfolio_equity: float
    peak_equity: float

class MantisRewardCalculator:
    
    OPTIMAL_TRADE_DURATION = 12    # candle ottimali per scalping (es. 12 × 5min = 1h)
    MAX_DAILY_TRADES = 8           # oltre questo → overtrading
    MAX_DRAWDOWN_ALLOWED = 0.015   # 1.5% drawdown massimo per singolo trade
    
    def scalping_reward(self, state: EnvState, new_profit: float) -> float:
        """
        Reward principale MANTIS — ottimizzata per scalping BTC/USDT.
        
        Componenti:
        (+) Premio profitto rapido: profitti in < OPTIMAL_TRADE_DURATION candle
        (+) Premio win rate elevato (reward shape verso alta frequenza di wins)
        (+) Premio trading in regime ad alta confidence HMM
        (-) Penalità drawdown: esponenziale oltre MAX_DRAWDOWN_ALLOWED
        (-) Penalità overtrading: lineare oltre MAX_DAILY_TRADES
        (-) Penalità durata eccessiva: lineare dopo OPTIMAL_TRADE_DURATION
        (-) Penalità trading in regime UNKNOWN o bassa confidence
        """
        base_profit = new_profit / self.MAX_DRAWDOWN_ALLOWED  # normalizzato
        
        # Penalità durata
        duration_penalty = -0.005 * max(0, state.trade_duration - self.OPTIMAL_TRADE_DURATION)
        
        # Penalità overtrading
        overtrading_penalty = -0.05 * max(0, state.daily_trade_count - self.MAX_DAILY_TRADES)
        
        # Bonus regime favorevole
        regime_bonus = state.hmm_confidence * 0.3 if state.hmm_regime != 4 else -0.5
        
        # Penalità drawdown esponenziale
        current_dd = (state.peak_equity - state.portfolio_equity) / state.peak_equity
        dd_penalty = -2.0 * (current_dd / self.MAX_DRAWDOWN_ALLOWED) ** 2 if current_dd > 0 else 0
        
        return base_profit + duration_penalty + overtrading_penalty + regime_bonus + dd_penalty
    
    def calmar_reward(self, state: EnvState, new_profit: float) -> float:
        """
        Reward alternativa basata su Calmar ratio incrementale.
        Usata per confronto e ensemble.
        """
        ...
```

### Task 4.3 — Training Pipeline RL

Crea `mantis/rl/trainer.py`:

```python
# MANTIS-P23: RL Training Pipeline con stable-baselines3

from stable_baselines3 import PPO, SAC
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback

class MantisRLTrainer:
    """
    Addestra agenti PPO e SAC sull'ambiente MANTIS.
    PPO: più stabile, adatto a strategy con reward sparsa
    SAC: più efficiente, adatto a spazi d'azione continui (adattato al discreto)
    
    Training schedule:
    - Retraining completo: settimanale (domenica 02:00 UTC)
    - Fine-tuning: ogni 24h su finestra mobile 30 giorni
    - Checkpoint: ogni 10.000 steps su disco
    """
    
    PPO_CONFIG = {
        "learning_rate": 3e-4,
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "gamma": 0.99,
        "ent_coef": 0.01,   # incoraggia esplorazione
    }
    
    def train(self, env: MantisRLEnvironment, total_timesteps: int = 500_000) -> None:
        ...
    
    def fine_tune(self, env: MantisRLEnvironment, timesteps: int = 50_000) -> None:
        """Fine-tuning giornaliero su dati recenti."""
        ...
    
    def schedule_retraining(self) -> None:
        """Schedula retraining automatico via APScheduler."""
        ...
```

**Dipendenze da aggiungere:**
```
stable-baselines3>=2.3.0
gymnasium>=0.29.0
```

### Task 4.4 — Ensemble XGBoost + RL

Crea `mantis/ensemble/xgb_rl_ensemble.py`:

```python
# MANTIS-P23: Ensemble XGBoost + RL
# XGBoost decide la direzione, RL ottimizza timing e sizing

class MantisEnsemble:
    """
    Logica di ensemble:
    1. XGBoost → probabilità direzione (prob_long, prob_short)
    2. RL → azione ottimale dato lo stato corrente
    3. Ensemble voting:
       - Concordanza XGB + RL stesso verso → segnale FORTE (sizing 100%)
       - Solo XGB segnale, RL neutro → segnale MODERATO (sizing 50%)
       - Discordanza XGB vs RL → NO_TRADE (prevale cautela)
    4. Regime gate (Sprint 1) → override finale
    """
    
    def predict(self, features_df: pl.DataFrame) -> EnsembleSignal:
        ...
```

### Criteri di completamento Sprint 4

- [ ] Ambiente Gym che passa `check_env()` senza errori
- [ ] Reward function `scalping_reward` implementata con tutti i componenti
- [ ] Agente PPO addestrato su training set storico (min 500k steps)
- [ ] Backtesting comparativo: XGBoost solo vs XGBoost+RL su validation set
- [ ] Retraining automatico schedulato (APScheduler)
- [ ] Checkpoint e model versioning su disco
- [ ] Ensemble logic implementata con tutti e tre i casi (forte/moderato/no_trade)

---

## Sprint 5 — Liquidations Heatmap Integration

### Obiettivo

Integrare i dati di liquidation zone da CoinGlass per aggiungere contesto strutturale
su dove il prezzo BTC ha alta probabilità di essere attratto a breve termine.

### Contesto: perché le liquidation zone sono alpha reale

In un mercato di perpetual futures ad alta leva, i market maker e le borse stesse
hanno incentivi a muovere il prezzo verso le zone di maggiore open interest
(dove si concentrano le liquidazioni). Il pattern è statisticamente significativo
su timeframe 15m-4h e non è riproducibile con indicatori classici.

### Fonte dati

**CoinGlass API** (tier gratuito o Basic):
- `GET /api/futures/liquidation/map/v2` → heatmap liquidazioni
- `GET /api/futures/openInterest/chart` → OI per livello di prezzo
- `GET /api/futures/longShortRatio` → long/short ratio aggregato per exchange

### Task 5.1 — CoinGlass Fetcher

Crea `mantis/data/coinglass_fetcher.py`:

```python
# MANTIS-P23: CoinGlass API Integration

class CoinGlassFetcher:
    """
    Fetcha e normalizza dati CoinGlass per BTC.
    Rate limit: rispettare i limiti del tier sottoscritto.
    Cache locale: aggiorna ogni 15 minuti.
    """
    
    BASE_URL = "https://open-api.coinglass.com/public/v2"
    
    async def fetch_liquidation_heatmap(self, timeframe: str = "4h") -> pl.DataFrame:
        """
        Ritorna DataFrame con:
        [price_level, liquidation_volume_usd, is_long_liq, is_short_liq, 
         distance_from_current_pct, strength_score]
        """
        ...
    
    async def fetch_oi_by_price_level(self) -> pl.DataFrame:
        """
        OI aggregato per livello di prezzo.
        Feature derivate: oi_concentration_above, oi_concentration_below
        """
        ...
    
    async def fetch_long_short_ratio(self) -> dict:
        """
        Long/short ratio per exchange (Bybit, Binance, OKX aggregati).
        """
        ...
```

### Task 5.2 — Liquidation Feature Engineering

Crea `mantis/features/liquidation_features.py`:

```python
# MANTIS-P23: Liquidation Zone Features

class LiquidationFeatureBuilder:
    """
    Feature generate:
    
    Proximity features:
    - nearest_long_liq_pct      : distanza % dalla prossima zona long liq
    - nearest_short_liq_pct     : distanza % dalla prossima zona short liq
    - liq_imbalance             : differenza volume long_liq vs short_liq vicine
    
    Attraction features:
    - price_in_liq_magnet       : bool, prezzo a < 0.5% da zona liq significativa
    - liq_magnet_direction      : +1 (sopra), -1 (sotto), 0 (nessuno)
    - liq_magnet_strength       : score 0.0-1.0 della forza di attrazione
    
    OI features:
    - oi_wall_above             : volume OI più grande sopra il prezzo (resistenza)
    - oi_wall_below             : volume OI più grande sotto il prezzo (supporto)
    - oi_concentration_ratio    : OI sopra / OI sotto (> 1 → più OI sopra)
    
    Sentiment features:
    - ls_ratio_current          : long/short ratio corrente aggregato
    - ls_ratio_7d_avg           : media 7 giorni
    - ls_ratio_extreme          : bool, > 0.7 o < 0.3
    """
    
    def build_features(
        self,
        main_df: pl.DataFrame,
        heatmap_df: pl.DataFrame,
        oi_df: pl.DataFrame,
        ls_ratio: dict
    ) -> pl.DataFrame:
        ...
```

### Criteri di completamento Sprint 5

- [ ] CoinGlass fetcher con cache 15 minuti e gestione rate limit
- [ ] Tutte le 11 liquidation feature implementate
- [ ] Feature aggiunte al modello XGBoost (retraining richiesto)
- [ ] Backtesting: confronto performance con/senza liquidation features
- [ ] Dashboard endpoint `GET /api/liquidations/current` con zone attive

---

## Sprint 6 — Multi-Agent Debate Layer

### Obiettivo

Aggiungere un layer di debate tra agenti specializzati che produce una raccomandazione
finale consensus come ultimo filtro prima dell'esecuzione.

**Posizionamento**: si attiva DOPO che il gate (Sprint 1), il funding check (Sprint 2)
e l'ensemble XGB+RL (Sprint 4) hanno già prodotto un segnale positivo.
Il debate è l'ultimo step di confidence building, non il primo.

### Task 6.1 — Agent Definitions

Crea `mantis/agents/specialized_agents.py`:

```python
# MANTIS-P23: Specialized Trading Agents

class TechnicalAgent:
    """Valuta il segnale da prospettiva tecnica: OFI, VPIN, Hawkes, regime HMM."""
    
class FundingAgent:
    """Valuta il segnale da prospettiva funding rate e posizionamento."""
    
class LiquidationAgent:
    """Valuta il segnale da prospettiva zone di liquidazione e OI."""
    
class RiskAgent:
    """
    Agente di rischio — può sempre bloccare il trade.
    Valuta: drawdown corrente, esposizione, volatilità realizzata, 
            correlazione con posizioni aperte.
    """
    
class MacroAgent:
    """Valuta contesto macro: FRED, Fear&Greed, news sentiment da Finnhub."""
```

### Task 6.2 — Debate Orchestrator

Crea `mantis/agents/debate_orchestrator.py`:

```python
# MANTIS-P23: Debate Orchestrator

@dataclass
class AgentVote:
    agent_name: str
    vote: str          # "BULL", "BEAR", "NEUTRAL", "BLOCK"
    confidence: float  # 0.0-1.0
    reasoning: str     # spiegazione breve per audit trail

@dataclass  
class DebateResult:
    final_decision: str        # "EXECUTE", "NO_TRADE"
    consensus_confidence: float
    votes: list[AgentVote]
    dissenting_agents: list[str]
    audit_trail: dict          # per logging completo

class MantisDebateOrchestrator:
    """
    Regole di voto:
    - Se RiskAgent vota BLOCK → NO_TRADE (veto assoluto)
    - Se 3+ agenti su 5 concordano (BULL o BEAR) → EXECUTE con confidence media
    - Se split 2-2-1 o simili → NO_TRADE (incertezza = astensione)
    
    Il debate NON usa LLM in produzione live (latenza incompatibile con scalping).
    Usa logica deterministica basata su regole derivate dai segnali di ciascun agente.
    Opzionale: LLM per analisi batch post-mercato (non in real-time).
    """
    
    def run_debate(self, market_state: dict) -> DebateResult:
        ...
```

### Criteri di completamento Sprint 6

- [ ] Tutti e 5 gli agenti implementati con logica deterministica
- [ ] Veto RiskAgent funzionante e testato
- [ ] Audit trail completo salvato su DB per ogni trade
- [ ] Backtesting con/senza debate layer su dati 2024
- [ ] Dashboard `GET /api/agents/last-debate` con ultimo debate visualizzato

---

## 10. Regole Globali e Anti-Pattern

### Regole architetturali

```
✅ Estendi, non riscrivere — ogni modulo nuovo è additivo rispetto a Phase 22
✅ Usa Polars ovunque — niente Pandas nel codice nuovo
✅ Ogni modulo nuovo ha test unitari con copertura > 80%
✅ Ogni breaking change ha MIGRATION_NOTE.md nello stesso PR
✅ Tutta la nuova logica è taggata # MANTIS-P23: nei commenti
✅ Feature engineering: aggiungi colonne, non modificare quelle esistenti
✅ generate_signal() originale rimane intatta — usa wrapper pattern
```

### Anti-pattern da evitare

```
❌ Non toccare il contratto XGBoost esistente senza migration script
❌ Non aggiungere LLM in hot path di esecuzione live (latenza)
❌ Non skippare Sprint 3 per procedere con Sprint 4
❌ Non guardare il test set prima della valutazione finale
❌ Non implementare RL senza check_env() che passa pulito
❌ Non fare retraining intra-day (troppo rumore, overfitting)
❌ Non usare leverage > 5x in nessuna strategia RL
```

### File da creare durante gli sprint

```
mantis/
├── regime/
│   ├── __init__.py
│   ├── hmm_detector.py          (Sprint 1)
│   ├── drift_monitor.py         (Sprint 1)
│   └── training_distributions.pkl (Sprint 1, generato)
├── data/
│   ├── funding_rate_fetcher.py  (Sprint 2)
│   └── coinglass_fetcher.py     (Sprint 5)
├── features/
│   ├── funding_features.py      (Sprint 2)
│   └── liquidation_features.py  (Sprint 5)
├── validation/
│   ├── walk_forward.py          (Sprint 3)
│   ├── backtester.py            (Sprint 3)
│   └── report_generator.py      (Sprint 3)
├── rl/
│   ├── environment.py           (Sprint 4)
│   ├── reward_functions.py      (Sprint 4)
│   └── trainer.py               (Sprint 4)
├── ensemble/
│   └── xgb_rl_ensemble.py       (Sprint 4)
└── agents/
    ├── specialized_agents.py    (Sprint 6)
    └── debate_orchestrator.py   (Sprint 6)
```

---

## 11. Criteri di Completamento Globali

### Gate finale — Phase 23 completata quando:

- [ ] **Sprint 1**: Regime gate attivo in produzione con monitoring dashboard
- [ ] **Sprint 2**: Funding rate features nel modello, contrarian signal validato
- [ ] **Sprint 3**: Walk-forward report con risultati reali, gate PASSED
- [ ] **Sprint 4**: Ensemble XGBoost+RL in produzione con retraining automatico
- [ ] **Sprint 5**: Liquidation features nel modello, CoinGlass integrato
- [ ] **Sprint 6**: Debate layer attivo con audit trail completo

### Metriche target Phase 23 (valutate su test set vergine)

```
Annualized Return:   > 35%
Sharpe Ratio:        > 1.2
Max Drawdown:        < -18%
Win Rate:            > 52%
Profit Factor:       > 1.6
Avg Trade Duration:  < 4 ore (mantenimento focus scalping)
```

### Come usare questo prompt contract con Claude Code

1. Apri il repository MANTIS in Claude Code
2. Carica questo file come contesto iniziale
3. Esegui un sprint alla volta — non procedere al successivo senza completare i criteri
4. Prima di Sprint 4, mostrare a Claude Code i risultati reali del Walk-Forward (Sprint 3)
5. Per ogni sprint: implementa → testa → backtesta → documenta → poi passa al successivo

---

*MANTIS AI — Phase 23: Resilience-First Evolution*
*Generato da analisi strategica — Marzo 2026*
*Priorità: Regime Awareness > Data Quality > Adaptability > Complexity*
