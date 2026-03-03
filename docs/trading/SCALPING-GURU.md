# MANTIS AI — Scalping Knowledge Base & Sources

> Documento di riferimento per l'arricchimento della knowledge base di MANTIS AI sullo scalping algoritmico. Organizzato per livello di profondità: dalla teoria fondamentale alla implementazione pratica.

---

## 1. FONDAMENTI TEORICI — Market Microstructure

Queste sono le basi scientifiche su cui costruire qualsiasi strategia di scalping seria. Lo scalping algoritmico non è "indicatori su un grafico" — è microstructure trading.

### 1.1 Paper Accademici Fondamentali

| Paper | Autori | Tema Chiave | URL |
|-------|--------|-------------|-----|
| **The Price Impact of Order Book Events** | Cont, Kukanov, Stoikov (2010) | Relazione quasi-lineare tra Order Flow Imbalance e movimenti di prezzo a breve termine | https://arxiv.org/abs/1011.6402 |
| **Queue Imbalance as a One-Tick-Ahead Predictor** | Gould, Bonart | Queue imbalance al best bid/offer predice il prossimo movimento del mid-price | Ricerca su Google Scholar |
| **Predicting Returns with Order Book and Trade Imbalances** | Aït-Sahalia et al. (2022) | Previsione rendimenti tramite imbalance order book | Ricerca su Google Scholar |
| **Market Microstructure Knowledge Needed for Controlling Intraday Trading** | Lehalle et al. | Modelli di microstruttura per ottimizzazione esecuzione ordini | https://arxiv.org/pdf/1302.4592 |
| **Forecasting High Frequency Order Flow Imbalance Using Hawkes Processes** | (2024) | Modellazione order flow come processo di conteggio con auto-eccitazione | https://arxiv.org/html/2408.03594v1 |
| **Cooperative Multi-Agent RL Framework for Scalping Trading** | Uk Jo et al. | Framework RL multi-agente per scalping con Conv3D su order book | https://arxiv.org/abs/1904.00441 |
| **Optimal Execution with Short-Term Signals** | Bank, Cartea, Körber | Modello di controllo stocastico per anticipare order flow | https://arxiv.org/pdf/2306.00621 |
| **An Analytical Framework for Real-Time Gold Trading Using Sentiment and Time-Series Forecasting** | (2025) | Modello ibrido LSTM + FinBERT sentiment per XAUUSD | https://www.sciencedirect.com/science/article/pii/S277266222500089X |

### 1.2 Concetti Chiave da Padroneggiare

- **Order Flow Imbalance (OFI)**: asimmetria tra ordini buy e sell — il singolo predittore più potente per movimenti di prezzo a brevissimo termine
- **VPIN (Volume-Synchronized Probability of Informed Trading)**: misura la tossicità del flow senza parametri non osservabili
- **Toxic Flow**: flow dove gli ordini resting vengono riempiti più velocemente del previsto — segnale di informed trading contro uninformed
- **PIN (Probability of Informed Trading)**: probabilità che un trader informato stia operando
- **Hawkes Processes**: modelli di punto per catturare il clustering degli arrivi di ordini
- **Queue Priority & Book Depth**: la posizione nella coda e la profondità del libro determinano la probabilità di esecuzione

### 1.3 Libri di Riferimento

| Libro | Autori | Focus |
|-------|--------|-------|
| **Trades, Quotes and Prices: Financial Markets Under the Microscope** | Bouchaud, Bonart, Donier, Gould (2018) | IL riferimento definitivo sulla microstruttura dei mercati |
| **Market Microstructure: Intermediaries and the Theory of the Firm** | Daniel Spulber (1999) | Teoria fondamentale della microstruttura |
| **Market Microstructure and Algorithmic Trading** | Venice Trex | Order flow, liquidity, execution tactics per quant |
| **Algorithmic Trading and DMA** | Barry Johnson | Accesso diretto al mercato e strategie di esecuzione |
| **Trading and Exchanges: Market Microstructure for Practitioners** | Larry Harris | Microstruttura pratica per operatori |

---

## 2. BLOG & RISORSE TECNICHE AVANZATE

### 2.1 Quantitative Research

| Risorsa | URL | Contenuto |
|---------|-----|-----------|
| **Jonathan Kinlay — Quantitative Research and Trading** | https://jonathankinlay.com/category/market-microstructure/ | Analisi approfondita scalping vs market making, toxic flow, VPIN, strategie HFT in futures. Kinlay gestisce Systematic Strategies, firma di prop trading HFT |
| **Jonathan Kinlay — Order Flow** | https://jonathankinlay.com/category/market-microstructure/order-flow/ | Focus specifico su order flow e suoi usi predittivi |
| **Jonathan Kinlay — Toxic Flow** | https://jonathankinlay.com/category/market-microstructure/toxic-flow/ | Analisi del flow tossico e protezione dello scalper |
| **Strange Matters — The Resilience of Order Flow** | https://strangematters.coop/how-financial-markets-work-market-microstructure-order-flow-theorists/ | Spiegazione dettagliata di order flow, LOB, liquidity, slippage per non-accademici |
| **Global Trading — Must-Read Microstructure Papers** | https://www.globaltrading.net/four-must-read-market-microstructure-papers-you-might-have-missed/ | Curated list di paper recenti sulla microstruttura |

### 2.2 Scalping Specifico per Gold (XAUUSD)

Dato il tuo interesse per il leveraged gold trading, queste sono risorse specifiche:

| Risorsa | Focus | Note |
|---------|-------|------|
| **TradingView — XAUUSD Indicators & Strategies** (https://www.tradingview.com/scripts/xauusd/) | Strategie open-source per XAUUSD | Include session detection, VWAP, ATR-based TP/SL, kill zones |
| **Gold AI: Hyper-Frequency 1min Scalper** (https://www.tradingview.com/script/z6KsrpPN-Gold-AI-Hyper-Frequency-1minute-Scalper/) | Lorentzian Distance Classifier per scalping gold 1m | Machine learning approach su pattern storici, profit scaling a 3 stadi |
| **XAUUSD 1-Min Scalping Strategy — Mean Reversion** (https://www.tradingview.com/script/0DLK91nb-XAUUSD-1-Minute-Scalping-Strategy-Advanced-Strategy-for-Exits/) | RSI(14) + EMA 200 mean reversion | Con dashboard live: P&L, win rate, profit factor, RSI |

### 2.3 Concetti Chiave per Gold Scalping

- **Session Awareness**: Asian (consolidamento, low ATR 3-5 pips M15), London (trend initiation, breakout), NY (massima volatilità, news)
- **Kill Zones**: London 08:00-10:00 GMT, NY 13:00-15:00 GMT — massima probabilità di setup validi
- **ATR-Based Position Sizing**: Stop-loss = 1.5-2x ATR corrente; position size = (Risk% × Account) / (SL in pips × pip value)
- **Dynamic TP/SL**: TP e SL NON fissi ma ancorati alla volatilità corrente (ATR)
- **Kelly Criterion / Half-Kelly**: per position sizing ottimale sul lungo termine
- **Correlazioni**: XAUUSD si muove inversamente a DXY, USD yields, e reagisce a NFP, CPI, FOMC

---

## 3. STRATEGIE ALGORITMICHE IMPLEMENTABILI

### 3.1 Architettura Tipica di uno Scalper Algoritmico

```
INPUT LAYER
├── Price Data (OHLCV, tick data)
├── Order Book Data (bid/ask depth, imbalance)
├── Volume Profile (CVD, VWAP deviations)
├── Volatility Regime (ATR, Bollinger Width, realized vol)
└── Session/Time Context (kill zones, news calendar)

SIGNAL LAYER
├── Trend Filter (EMA 200, EMA 55 per contesto direzionale)
├── Mean Reversion Detector (RSI extremes, Bollinger touch, z-score)
├── Momentum Scorer (MACD histogram slope, Stochastic %K/%D)
├── Order Flow Analyzer (OFI, VPIN, book imbalance ratio)
└── Volume Confirmation (volume > avg, CVD direction alignment)

DECISION LAYER
├── Weighted Score Aggregation (pesi configurabili per ogni segnale)
├── Regime Detection (trending vs ranging vs choppy)
├── Confluence Check (minimo N segnali concordanti)
└── Confidence Threshold (score minimo per entry)

EXECUTION LAYER
├── Entry (limit vs market, timing optimization)
├── Position Sizing (ATR-based, Kelly fraction)
├── Stop Loss (dynamic, ATR-based, sotto noise level)
├── Take Profit (multi-stage: TP1 quick scalp, TP2 extension, TP3 moonshot)
├── Trailing Stop (ATR-based trail, breakeven dopo TP1)
└── Time-Based Exit (max holding period, session close)

RISK MANAGEMENT LAYER
├── Max Risk Per Trade (0.5-1.5% account)
├── Max Daily Drawdown (circuit breaker)
├── Max Correlated Exposure (gold positions = singola unità di rischio)
├── Max Trades Per Day (evita overtrading)
└── News Filter (riduce size o sospende pre-NFP/FOMC)
```

### 3.2 Strategie Specifiche da Implementare

#### A) EMA Crossover + VWAP Filter
- **Entry Long**: EMA(9) cross sopra EMA(21) + prezzo sopra VWAP
- **Entry Short**: EMA(9) cross sotto EMA(21) + prezzo sotto VWAP
- **SL**: 1.5x ATR(14)
- **TP**: 1:1.5 R:R minimo
- **Timeframe**: 1m-5m
- **Filtro**: Solo durante London/NY kill zones

#### B) RSI Mean Reversion con Trend Filter
- **Entry Long**: RSI(14) < 30 + prezzo sopra EMA(200)
- **Entry Short**: RSI(14) > 70 + prezzo sotto EMA(200)
- **SL**: Fixed pips o ATR-based
- **TP**: Ritorno verso media (EMA 20 o VWAP)
- **Win rate atteso**: 55-70% con profit factor > 1.4

#### C) Order Flow Imbalance Scalper
- **Calcola OFI**: delta tra volume bid e ask in finestra temporale
- **EMA su OFI**: smoothing per signal generation
- **Entry**: OFI estremo + conferma di book depth asymmetry
- **Edge**: predittivo 10-60 secondi, ideale per scalping
- **Requisito**: accesso a Level 2 data o tick data

#### D) Volatility Breakout dopo Compressione
- **Identifica**: Bollinger Band width ai minimi (squeeze)
- **Attendi**: breakout con volume sopra media
- **Entry**: nella direzione del breakout
- **TP**: 1x larghezza della compressione
- **Filtro**: Allinea con trend EMA(55) per evitare falsi breakout

#### E) Multi-Timeframe Confluence
- **HTF (15m-1h)**: Identifica bias direzionale (trend, S/R key levels)
- **MTF (5m)**: Conferma setup (pattern, indicator alignment)
- **LTF (1m)**: Entry precision con timing ottimale
- **Principio**: trade solo quando tutti e 3 i TF concordano

---

## 4. REPO GITHUB & IMPLEMENTAZIONI DI RIFERIMENTO

### 4.1 Repository con Codice Funzionante

| Repo | Linguaggio | Focus | URL |
|------|-----------|-------|-----|
| **Alpaca Example Scalping** | Python | Scalping multi-stock con asyncio, state machine | https://github.com/alpacahq/example-scalping |
| **Scalping Bots (msolomos)** | Python | MACD, RSI, Bollinger, VWAP, ATR, Stochastic + weighted scoring | https://github.com/msolomos/scalping-bots |
| **SyDOM — Order Imbalance Scalper** | Python | RSI su delta bid/sell + Bollinger filter + ML module | https://github.com/5ymph0en1x/SyDOM |
| **EMA-VWAP Crossover Bot** | Python | Entry su EMA crossover con VWAP filter | https://github.com/vishnugovind10/emacrossover |
| **Algo Trading EMA-VWAP** | Python | Monitor automatico VWAP + EMA con ordini auto | https://github.com/Swastik2000/Algo-Trading-Through-EMA-VWAP |
| **RSI Scalping Backtester** | Python | Backtesting RSI su 1-5-15m con TP/SL percentuali | https://github.com/asier13/Python-Trading-Bot |
| **GitHub Topic: Scalping** | Vari | Collezione di repo tagged "scalping" | https://github.com/topics/scalping |
| **GitHub Topic: VWAP** | Vari | Repo con implementazioni VWAP | https://github.com/topics/vwap |

### 4.2 Librerie Python Essenziali

```
# Technical Analysis
ta-lib          # C-backed, velocissimo per indicatori classici
pandas-ta       # Alternativa pure Python, 130+ indicatori
tulipy          # Binding Python per Tulip Indicators (C)

# Backtesting
backtrader      # Framework completo per backtesting
vectorbt        # Backtesting vettorizzato ultra-veloce con pandas
zipline-reloaded # Ex-Quantopian, ora open source

# Data & Execution
ccxt            # Unified API per 100+ exchange crypto
alpaca-trade-api # Broker API per US equities
capital-com-client # Per Capital.com (il tuo broker)

# Machine Learning per Trading
stable-baselines3 # RL algorithms (PPO, A2C, SAC) per trading env
gymnasium       # Environment per RL trading
scikit-learn    # Feature engineering, clustering, classification

# Order Book & Market Data
orderbook       # Fast limit order book implementation
lobster-data    # Per dati LOBSTER (Limit Order Book System)
```

---

## 5. METRICHE & KPI PER VALUTAZIONE STRATEGIA

### 5.1 Metriche Obbligatorie

| Metrica | Target Scalping | Descrizione |
|---------|----------------|-------------|
| **Sharpe Ratio** | > 3.0 (ideale 3-5) | Rendimento aggiustato per rischio. Sotto 2 = non competitivo per scalping |
| **Profit Factor** | > 1.4 | Gross profit / Gross loss. Sotto 1.2 non copre i costi |
| **Win Rate** | 55-70% | Con R:R 1:1.5 serve almeno 55% |
| **Max Drawdown** | < 10% | Circuit breaker se superato |
| **Average Trade Duration** | < 5 min | Se supera i 15 min non è più scalping |
| **Trades/Day** | 10-50 | Sotto 10 = non abbastanza campione, sopra 100 = overtrading |
| **Expectancy** | > 0 | (Win% × AvgWin) - (Loss% × AvgLoss) > costi transazione |
| **Recovery Factor** | > 3 | Net Profit / Max Drawdown |
| **Calmar Ratio** | > 2 | Annual Return / Max Drawdown |

### 5.2 Costi da Considerare (SEMPRE)

- **Spread**: su XAUUSD tipicamente 0.2-0.5 pips (broker ECN)
- **Commission**: variabile per broker, tipicamente $3-7 per lotto round-turn
- **Slippage**: 2-5 ticks su 1m chart in condizioni normali, molto peggio in news
- **Swap/Financing**: se si tiene overnight (da evitare nello scalping puro)
- **Impatto cumulativo**: con 50 trade/giorno, anche 0.3 pip di spread = 15 pips/giorno di costo fisso

---

## 6. REGIME DETECTION — L'Arma Segreta

Il singolo miglioramento più impattante per MANTIS AI è la **detection del regime di mercato** per switchare strategia automaticamente.

### 6.1 Regimi da Identificare

| Regime | Indicatori | Strategia Ottimale |
|--------|------------|-------------------|
| **Trending** | ADX > 25, EMA alignment, Bollinger expanding | Momentum/Trend following |
| **Ranging** | ADX < 20, prezzo dentro Bollinger, bassa volatilità | Mean reversion, range scalping |
| **Volatile/Choppy** | ATR spike, ADX basso ma Bollinger wide | Ridurre size, wider stops, o stare fuori |
| **Breakout** | Bollinger squeeze → expansion, volume spike | Breakout scalping con conferma volume |
| **News-Driven** | Pre/post NFP, FOMC, CPI | Ridurre drasticamente o sospendere |

### 6.2 Implementazione Suggerita

```python
# Pseudo-codice per regime detection
def detect_regime(candles, period=20):
    atr = calc_ATR(candles, period)
    adx = calc_ADX(candles, period)
    bb_width = calc_bollinger_width(candles, period)
    bb_width_percentile = percentile_rank(bb_width, lookback=100)
    
    if adx > 25 and bb_width_percentile > 70:
        return "TRENDING"
    elif adx < 20 and bb_width_percentile < 30:
        return "RANGING"  
    elif bb_width_percentile < 10:
        return "SQUEEZE"  # Possibile breakout imminente
    elif atr > atr_mean * 2:
        return "HIGH_VOLATILITY"  # Cautela
    else:
        return "NEUTRAL"
```

---

## 7. CHECKLIST IMPLEMENTAZIONE PER MANTIS AI

### Fase 1: Fondamenta
- [ ] Implementare calcolo ATR dinamico per position sizing
- [ ] Aggiungere session detection (Asian/London/NY con kill zones)
- [ ] Implementare regime detector basico (ADX + BB width)
- [ ] Creare sistema di weighted scoring per segnali

### Fase 2: Signal Engine
- [ ] EMA crossover con VWAP filter
- [ ] RSI mean reversion con trend filter
- [ ] Bollinger squeeze detector
- [ ] Multi-timeframe confluence checker

### Fase 3: Execution & Risk
- [ ] Dynamic TP/SL basati su ATR
- [ ] Trailing stop con breakeven automatico
- [ ] Multi-stage profit taking (TP1/TP2/TP3)
- [ ] Circuit breaker per max daily drawdown
- [ ] News calendar filter (sospensione pre-event)

### Fase 4: Avanzato
- [ ] Order Flow Imbalance (se disponibile via API)
- [ ] Volatility regime switching automatico
- [ ] ML-based pattern recognition (Lorentzian Distance o simili)
- [ ] RL agent per ottimizzazione parametri
- [ ] Backtesting framework con costi realistici

---

## 8. NOTE PER CLAUDE CODE

Quando lavori su MANTIS AI con questo documento come riferimento:

1. **Ogni strategia DEVE includere costi di transazione nel backtest** — spread, commission, slippage. Senza questi, qualsiasi backtest è fiction.

2. **Position sizing SEMPRE dinamico** — basato su ATR corrente, MAI fisso in lotti.

3. **Stop loss SEMPRE fuori dal rumore** — minimo 1.5x ATR, mai arbitrario.

4. **Regime detection PRIMA di qualsiasi segnale** — se il regime è "choppy" o "high volatility news", la strategia deve ridurre size o stare fuori.

5. **Session awareness è NON-NEGOTIABLE** — scalping gold durante la sessione asiatica con gli stessi parametri della sessione NY è un errore sistematico.

6. **Ogni modifica deve essere backtestabile** — no "intuizioni", solo ipotesi testabili con dati storici.

7. **Target Sharpe Ratio > 3** — sotto questo livello la strategia non giustifica il rischio dello scalping.

---

*Documento generato il 3 marzo 2026 — Versione 1.0*
*Per aggiornamenti: ricercare nuovi paper su arxiv.org/search con query "market microstructure scalping order flow"*