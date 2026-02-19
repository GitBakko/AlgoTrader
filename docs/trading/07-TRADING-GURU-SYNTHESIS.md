# Trading Guru Synthesis — ML Upgrade Plan

> Analisi risultante dallo studio approfondito di `docs/addestramento.md` e dell'intero codebase ML/Strategy.
> Data: 2026-02-11

---

## Diagnosi: Problemi Critici Identificati

### 1. BLOCCANTE — Confidence Threshold vs 5 Classi

**File coinvolti**: `src/strategy/schemas.py:43`, `src/models/schemas.py:12-23`, `src/models/target_builder.py`

**Il problema**: `StrategyConfig.min_confidence = 0.65` ma con 5 classi (STRONG_SELL/SELL/HOLD/BUY/STRONG_BUY) un modello XGBoost produce massimo ~0.30 di probabilità per classe. Il risultato: **il sistema non genera MAI segnali di trading — tutto diventa HOLD**.

Anche l'adattamento regime più aggressivo (trending_up → 0.60) è irraggiungibile.

**Impatto**: Il paper trading loop gira ma non produce alcun trade. L'intero pipeline da PredictionService → StrategyManager → ExecutionEngine è funzionalmente inattivo.

**Soluzione**: Migrare da 5 a 3 classi (SELL=0 / HOLD=1 / BUY=2):
- Concentra la massa probabilistica → confidence 0.50-0.80 raggiungibile
- Semplifica il task ML → F1 macro migliore (baseline attesa: 0.35-0.45 vs 0.20-0.24)
- Compatibile al 100% con il pipeline esistente (SignalGenerator già mappa a BUY/SELL/HOLD)
- I livelli "STRONG" vengono espressi via confidence: alta confidence (>0.75) = forte convinzione
- TargetBuilder usa soglia singola: |future_change| > 0.5 * ATR → BUY/SELL, altrimenti HOLD

### 2. Nessun LSTM/TFT — Solo XGBoost

Il piano in `03-ML-STRATEGY.md` prevede un ensemble LSTM + TFT + XGBoost con meta-learner. Attualmente solo XGBoost è implementato. Un singolo modello senza conferma cross-model è intrinsecamente meno affidabile.

### 3. Feature Set Limitato (~25 indicatori)

**Feature presenti**: EMA (4 periodi), MACD, ADX, RSI, Bollinger Bands, ATR, OBV, returns (3 lag), price action (2), hvol, crossover signals.

**Feature mancanti ma pianificate**:
- RSI divergence (segnale reversal più potente — Babson College TA, MIT/UPenn paper)
- Bollinger Squeeze (precursore esplosione volatilità — scalping materials)
- Stochastic RSI (più reattivo di RSI plain — Alpha Academy course)
- VWAP (Volume-Weighted Average Price — ML-HFT repos)
- Cross-asset features (Gold-DXY correlation, BTC-Gold, VIX per S&P)
- Multi-timeframe features (infrastruttura esiste in `TimeframeAligner` ma non attivata)

### 4. Nessuna Confidence Calibration

Le probabilità raw dal modello non sono calibrate. `03-ML-STRATEGY.md` menziona Platt scaling e isotonic regression, ma non sono implementate. Senza calibrazione, "0.40 confidence" non significa "40% di accuratezza storica".

---

## Conoscenze Acquisite dal Materiale di Addestramento

### Da Scalping & Day Trading Resources (Sezione 1)
- **EMA crossover strategies (50/100/200)**: conferma che le nostre EMA 8/21/50/200 sono standard. Aggiungere EMA 100 per crossover intermedio.
- **Risk-reward ratio minimo 1.5:1**: il nostro default è 2.0 (buono), ma il codice non lo applica in modo rigido durante la generazione del segnale.
- **Timeframe confirmation**: i segnali su timeframe superiori hanno più peso. Conferma l'importanza delle multi-timeframe features.
- **Session timing (London/NY)**: per Gold e S&P 500, la sessione di apertura è più volatile. Possibile feature: "hour_of_day" e "session" come input categorici.

### Da Technical Analysis & Chart Patterns (Sezione 2)
- **RSI Divergence** (Babson College): Implementabile algoritmicamente. Cercare swing highs/lows su prezzo e RSI, confrontare direzione.
- **Head-and-Shoulders detection** (MIT/UPenn paper di Lo): Algoritmo basato su kernel regression smoothing → identificazione pivot → pattern matching. Complesso ma potente. Più adatto come feature del TFT (sequence-aware).
- **Bollinger Band Squeeze** (Fidelity): `bb_width < threshold` → attesa espansione volatilità. Feature binaria semplice da aggiungere.
- **Pattern reliability** (Kirkpatrick, Swissquote): I pattern di continuazione (flag, pennant) hanno tasso di successo più alto dei pattern di inversione. Utile per pesare features.

### Da HFT & Machine Learning (Sezione 3)
- **AIMSPRESS paper**: 50 raw features da order book + 18 higher-level (aggregazione 5-min). SVM con kernel RBF ha outperformato RF su dati LOB. Per noi: l'aggregazione temporale delle features è importante.
- **ML-HFT repo (Bradley Yang)**: Orderbook Imbalance (OBI), Depth Ratio, Rise Ratio come features. LSTM combinato con classifiers classici via weighted averaging. **Tecnica chiave**: weighted signal averaging tra modelli diversi basato su performance recente.
- **Kearns & Nevmyvaka (UPenn)**: Reinforcement Learning per trading come alternativa alla classificazione. State-conditioned policies. Per il futuro (Phase 7+).
- **Stefan Jansen repo**: Gradient boosting con TA-Lib features, Alpha factor creation, Wavelets per denoising. Zipline backtesting. **Conferma**: il nostro approccio XGBoost + technical features è standard industriale. Mancano: Kalman filter, Wavelets per smoothing.

### Da Backtesting & Quantitative Trading (Sezione 4)
- **Walk-forward è il gold standard**: conferma il nostro approccio. Ma aggiungere: rolling window vs expanding window comparison.
- **Transaction costs e slippage**: il nostro BacktestEngine li simula, ma il paper loop non li considera. Aggiungere slippage estimate ai paper trades.
- **VectorBT**: per backtesting veloce di molte combinazioni di parametri. Potenziale tool per hyperparameter search.

### Da Bonus Resources (Sezione 5)
- **Confidence Calibration** (implicito in tutti i materiali avanzati): prerequisito per qualsiasi sistema di trading ML serio.
- **Feature Importance con SHAP**: per spiegare perché il modello fa certe previsioni. Dashboard feature.

---

## Piano Implementativo: Phase 6A — Trading Guru ML Upgrades

### Priorità e Ordine di Esecuzione

| Step | Descrizione | Impatto | Complessità | File |
|------|-------------|---------|-------------|------|
| 1 | Migrazione 5→3 classi | **CRITICO** | Bassa | 5 file |
| 2 | Confidence Calibration | **ALTA** | Bassa | 2 file nuovi |
| 3 | Nuove Feature Tecniche | **ALTA** | Media | 2 file |
| 4 | LSTM Model | **MEDIA** | Alta | 3 file nuovi |
| 5 | Multi-timeframe features | **MEDIA** | Bassa | 1 file |
| 6 | Re-training e validazione | **CRITICA** | Bassa | script |

### Step 1: Migrazione 5→3 Classi

**File da modificare:**
- `src/models/schemas.py` — `SignalClass` enum: SELL=0, HOLD=1, BUY=2
- `src/models/target_builder.py` — soglia singola: `|atr_relative| > 0.5` → BUY/SELL
- `src/models/xgboost_model.py` — `n_classes=3`
- `src/models/evaluator.py` — aggiornare labels
- `src/strategy/signal_generator.py` — semplificare mapping
- `src/models/prediction_service.py` — aggiornare
- Tests: aggiornare tutti i test che usano 5 classi

**Logica TargetBuilder aggiornata:**
```
future_change = close[t+6] - close[t]
atr_relative = future_change / ATR_14

if atr_relative > 0.5  → BUY (2)
if atr_relative < -0.5 → SELL (0)
else                    → HOLD (1)
```

### Step 2: Confidence Calibration

**File da creare:**
- `src/models/calibration.py` — wrapper per CalibratedClassifierCV

**Integrazione:**
- `ModelTrainer` → dopo training, calibra su validation set
- `PredictionService` → usa modello calibrato per predict_proba
- Calibrazione con metodo "isotonic" (non-parametrico, più flessibile di Platt)

### Step 3: Nuove Feature Tecniche

**File da modificare:**
- `src/features/technical.py` — aggiungere:
  - `add_rsi_divergence()` — detect bullish/bearish divergence
  - `add_bollinger_squeeze()` — bb_width sotto soglia
  - `add_stochastic_rsi()` — RSI di RSI
  - `add_vwap()` — Volume-Weighted Average Price
  - `add_session_features()` — hour_of_day, trading_session
- `src/features/builder.py` — integrare nuove features nel pipeline

### Step 4: LSTM Model

**File da creare:**
- `src/models/lstm_model.py` — PyTorch LSTM che estende BaseMLModel
  - Input: sequenze di feature vectors (shape: batch x seq_len x features)
  - Architecture: 2-layer LSTM, dropout 0.3, linear head → 3 classi
  - Trainer compatibility: fit(X_train, y_train) con reshape automatico

**Nota**: L'LSTM opera su sequenze, quindi richiede reshape dei dati. Il `ModelTrainer` dovrà gestire sia input tabellare (XGBoost) che sequenziale (LSTM).

### Step 5: Multi-Timeframe Features

**File da modificare:**
- `src/features/asset_config.py` — attivare `additional_timeframes: ["4h", "1d"]` per tutti gli asset
- Verificare che `TimeframeAligner` funzioni correttamente con dati reali

### Step 6: Re-training e Validazione

**Script da eseguire:**
```bash
# 1. Re-download dati (per avere ultimi aggiornamenti)
python scripts/download_data.py

# 2. Re-train modelli XGBoost con 3 classi
python scripts/train_models.py

# 3. Verificare F1 macro >= 0.35 (vs 0.20-0.24 con 5 classi)

# 4. Avviare paper trading e verificare che generi segnali
POST /api/trading/start
# Dopo 1h: GET /api/trading/status → verificare last_signals non vuoto
```

---

## Metriche Target Post-Upgrade

| Metrica | Baseline (5 classi) | Target (3 classi) | Target (ensemble) |
|---------|---------------------|--------------------|--------------------|
| F1 macro | 0.20-0.24 | 0.35-0.45 | 0.45-0.55 |
| Directional accuracy | ~60% | ~65% | ~70% |
| Trading signal rate | 0% (bug!) | >30% delle barre | >25% delle barre |
| Confidence range | 0.25-0.32 | 0.45-0.80 | 0.50-0.85 |
| Win rate (paper) | N/A | >50% | >55% |

---

## Note Architetturali

### Cosa NON cambia
- Pipeline generale: Data → Features → Model → Signal → Risk → Execution
- Walk-forward training approach
- ATR-based stop loss e position sizing
- Regime detection (ADX + EMA slope)
- Paper trading loop structure
- API endpoints e frontend

### Cosa cambia
- Numero classi: 5 → 3
- Feature count: ~25 → ~35 (con nuove TA features)
- Modelli: 1 (XGBoost) → 2 (XGBoost + LSTM) → 3 (+ TFT)
- Confidence: raw → calibrata
- Multi-timeframe: disattivato → attivato
