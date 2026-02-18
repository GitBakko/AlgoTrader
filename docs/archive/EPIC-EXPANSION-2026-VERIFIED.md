# MANTIS AI - EPIC Expansion 2026 (Verified)

**Date**: 2026-02-14
**Status**: ✅ ALL 12 CANDIDATES VERIFIED ON CAPITAL.COM
**Success Rate**: 100% (12/12 assets available)

---

## 🎯 Executive Summary

After comprehensive market research and Capital.com API verification, we identified **12 new tradable assets** to expand the MANTIS AI portfolio from 9 to **21 total assets**.

**Current Portfolio (9 assets):**
- XAUUSD (Gold)
- BTCUSD (Bitcoin)
- US500 (S&P 500)
- WTIUSD (WTI Crude Oil)
- EURUSD (Euro/Dollar)
- NVDA (NVIDIA)
- TSLA (Tesla)
- XAGUSD (Silver)
- DE40 (DAX 40)

**New Additions (12 assets):**
- 6 Crypto assets (Solana, Ethereum, BNB, Dogecoin, Dash, Internet Computer)
- 3 Commodities (Natural Gas, Copper, Platinum)
- 2 Forex pairs (GBP/USD, USD/JPY)
- 1 Index (Nasdaq 100)

---

## ✅ Verified EPIC Candidates (Capital.com API)

### 🪙 CRYPTO ASSETS (6/6 Available - 24/7 Trading)

| # | MANTIS Name | Capital.com EPIC | Market Name | Status | Trading | Priority |
|---|-------------|------------------|-------------|--------|---------|----------|
| 1 | SOLUSD | `SOLUSD` | Solana | ✅ TRADEABLE | 24/7 | ⭐⭐⭐ |
| 2 | ETHUSD | `ETHUSD` | Ethereum | ✅ TRADEABLE | 24/7 | ⭐⭐⭐ |
| 3 | BNBUSD | `BNBUSD` | Binance Coin | ✅ TRADEABLE | 24/7 | ⭐⭐ |
| 4 | DOGUSD | `DOGEUSD` | Dogecoin | ✅ TRADEABLE | 24/7 | ⭐⭐ |
| 5 | DASHUSD | `DASHUSD` | Dash | ✅ TRADEABLE | 24/7 | ⭐ |
| 6 | ICPUSD | `ICPUSD` | Internet Computer | ✅ TRADEABLE | 24/7 | ⭐ |

**Key Findings:**
- All 6 crypto assets tradeable 24/7 (no market hours restrictions)
- Solana ($85, $3.4B daily volume) overtook Ethereum in DEX volume ($117B vs $52B)
- Ethereum remains DeFi backbone (~$2000, $245B market cap)
- High volatility range: 3-8% intraday (ideal for scalping)

---

### 🏭 COMMODITIES (3/3 Available)

| # | MANTIS Name | Capital.com EPIC | Market Name | Status | Trading Hours | Priority |
|---|-------------|------------------|-------------|--------|---------------|----------|
| 7 | NATGAS | `NATURALGAS` | Natural Gas | ✅ Found | 24/5 | ⭐⭐⭐ |
| 8 | COPPER | `COPPER` | Copper | ✅ Found | 24/5 | ⭐⭐⭐ |
| 9 | PLATINUM | `PLATINUM` | Platinum | ✅ Found | 24/5 | ⭐ |

**Key Findings:**
- Natural Gas: **78.4% volatility spike** in Jan 2026 (extreme scalping opportunities)
- Copper: Supply deficit 1M tons, price at $13,238/ton (historical high), data center demand
- Platinum: Low correlation with Gold (~0.50), automotive/industrial demand
- All commodities CLOSED during verification (19:46 CET) - normal for overnight hours

---

### 💱 FOREX PAIRS (2/2 Available)

| # | MANTIS Name | Capital.com EPIC | Market Name | Status | Trading Hours | Priority |
|---|-------------|------------------|-------------|--------|---------------|----------|
| 10 | GBPUSD | `GBPUSD` | GBP/USD (Cable) | ✅ Found | 24/5 | ⭐⭐⭐ |
| 11 | USDJPY | `USDJPY` | USD/JPY | ✅ Found | 24/5 | ⭐⭐ |

**Key Findings:**
- GBP/USD: Highest liquidity among volatile pairs, spread 0.8-1.2 pips (0.006-0.009%)
- USD/JPY: Negative correlation with EURUSD (-0.40) → excellent diversification
- Both trading at ~1.37 (GBP) and influenced by central bank policy volatility
- Forex markets CLOSED during verification (weekend/overnight) - expected

---

### 📊 INDICES (1/1 Available)

| # | MANTIS Name | Capital.com EPIC | Market Name | Status | Trading Hours | Priority |
|---|-------------|------------------|-------------|--------|---------------|----------|
| 12 | NAS100 | `QTEC` | Nasdaq 100 | ✅ Found | 24/5 | ⭐⭐⭐ |

**Key Findings:**
- Capital.com uses `QTEC` as EPIC code for Nasdaq 100
- Forecast 2026: +7-12% (29,995-35,132 points)
- 55.4% tech composition, AI spending narrative
- High volatility 1.5-2.5% intraday (complementary to US500)
- Index CLOSED during verification - expected for overnight hours

---

## 📋 EPIC Mapping for Backend Configuration

Update `backend/src/broker/client.py` EPIC mapping:

```python
EPIC_TO_BROKER: dict[str, str] = {
    # Existing mappings
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "WTIUSD": "OIL_CRUDE",

    # NEW CRYPTO (use as-is, no mapping needed)
    # "SOLUSD": "SOLUSD",
    # "ETHUSD": "ETHUSD",
    # "BNBUSD": "BNBUSD",
    "DOGUSD": "DOGEUSD",  # Note: DOGE**USD** not DOGUSD
    # "DASHUSD": "DASHUSD",
    # "ICPUSD": "ICPUSD",

    # NEW COMMODITIES
    "NATGAS": "NATURALGAS",  # Natural Gas
    # "COPPER": "COPPER",
    # "PLATINUM": "PLATINUM",

    # NEW FOREX (use as-is)
    # "GBPUSD": "GBPUSD",
    # "USDJPY": "USDJPY",

    # NEW INDICES
    "NAS100": "QTEC",  # Nasdaq 100
}
```

**Important Notes:**
- Only 3 new EPICs require mapping: `DOGUSD→DOGEUSD`, `NATGAS→NATURALGAS`, `NAS100→QTEC`
- All other EPICs use identical names on Capital.com API
- Comment entries with `#` are direct 1:1 mappings (no translation needed)

---

## 🎯 Implementation Priority Tiers

### Tier 1 - Immediate Implementation (6 assets) ⭐⭐⭐

1. **SOLUSD** - Crypto leader, $117B DEX volume
2. **ETHUSD** - DeFi backbone, $245B market cap
3. **NATGAS** - Extreme volatility (78.4% spike)
4. **COPPER** - Supply deficit, institutional rotation
5. **GBPUSD** - Highest forex liquidity, tight spreads
6. **NAS100 (QTEC)** - AI narrative, tech-heavy

**Rationale**: Maximum diversification across all asset classes, proven volume, ideal volatility for scalping.

### Tier 2 - Secondary Implementation (4 assets) ⭐⭐

7. **BNBUSD** - Robust DeFi ecosystem
8. **DOGUSD** - Retail momentum, high volatility
9. **USDJPY** - Negative EURUSD correlation
10. **PLATINUM** - Precious metals diversification

**Rationale**: Additional portfolio depth, specific regime opportunities.

### Tier 3 - Future Consideration (2 assets) ⭐

11. **DASHUSD** - Privacy sector play
12. **ICPUSD** - Deflationary protocol

**Rationale**: Lower priority due to lower liquidity compared to Tier 1/2.

---

## 📊 Portfolio Diversification Analysis

### Before Expansion (9 assets)
- **Crypto**: 1 (11.1%) - Bitcoin only
- **Commodities**: 3 (33.3%) - Gold, Silver, Oil
- **Forex**: 1 (11.1%) - EURUSD
- **Stocks**: 2 (22.2%) - NVDA, TSLA
- **Indices**: 2 (22.2%) - US500, DE40

### After Expansion (21 assets)
- **Crypto**: 7 (33.3%) ⬆️ +600% representation
- **Commodities**: 6 (28.6%) ⬆️ +100% representation
- **Forex**: 3 (14.3%) ⬆️ +200% representation
- **Stocks**: 2 (9.5%) ⬇️ (relative decrease, absolute same)
- **Indices**: 3 (14.3%) ⬆️ +50% representation

**Key Improvements:**
- Crypto exposure increases from 11% to 33% (crypto focus achieved ✅)
- 24/7 trading capability increases from 11% to 38% (7 crypto assets)
- Low correlation assets: COPPER (0.40 vs GOLD), USDJPY (-0.40 vs EURUSD)
- Volatility range now spans 0.7% (forex) to 8% (crypto) - full spectrum coverage

---

## 🔧 Technical Implementation Checklist

### Phase 1: Backend Configuration (2h)

- [ ] Update `backend/src/broker/client.py` EPIC_TO_BROKER mapping
- [ ] Add 12 EPICs to `backend/.env` HISTORICAL_DATA_ASSETS list
- [ ] Create `backend/config/new_epics.yaml` with asset-specific parameters
- [ ] Update `backend/src/data/collectors.py` to handle new asset types

### Phase 2: Feature Engineering (3h)

- [ ] Verify technical indicators work for all 12 assets (RSI, MACD, Bollinger)
- [ ] Add crypto-specific features (on-chain metrics for SOL/ETH/BNB)
- [ ] Add commodity-specific features (seasonality for NATGAS, industrial demand for COPPER)
- [ ] Test feature extraction on historical data for each EPIC

### Phase 3: ML Model Extension (4h)

- [ ] Retrain XGBoost 3-class models for all 12 assets
- [ ] Run walk-forward optimization (WF OOS validation)
- [ ] Calibrate probability outputs (isotonic regression)
- [ ] Benchmark against existing 9 assets (expect F1 0.50-0.60)

### Phase 4: Risk Management Updates (2h)

- [ ] Configure asset-specific circuit breakers (crypto higher volatility thresholds)
- [ ] Update Kelly criterion parameters for higher volatility assets
- [ ] Set correlation matrix for 21 assets (position sizing constraints)
- [ ] Test trailing stop logic on 24/7 crypto markets

### Phase 5: Frontend Integration (3h)

- [ ] Add 12 EPICs to `frontend/src/app/core/models/index.ts`
- [ ] Update epic selector dropdown (group by category: Crypto, Commodities, Forex, Indices)
- [ ] Create category badges/icons for visual differentiation
- [ ] Test all 21 assets on Dashboard, Markets, Paper Trading views

### Phase 6: Testing & Validation (4h)

- [ ] Integration tests for all 12 new EPICs on Capital.com demo
- [ ] Verify data collection pipeline (OHLC fetching, storage)
- [ ] Backtest signals for 30 days historical data
- [ ] Paper trade 1 week on 3 high-priority assets (SOLUSD, NATGAS, GBPUSD)

**Total Estimated Time**: 18 hours (~2.5 days)

---

## 📈 Expected Performance Impact

### Opportunity Increase
- **Signal frequency**: +133% (21 assets vs 9) → more trading opportunities per day
- **24/7 trading**: 7 crypto assets always tradeable → weekend gaps eliminated
- **Volatility spectrum**: 0.7%-8% range → strategies for all market regimes

### Risk Considerations
- **Correlation risk**: Monitor Gold-Copper (0.40), BTC-SOL-ETH cluster (0.65-0.75)
- **Crypto volatility**: Require larger stop losses (8% swings), lower position sizing
- **Spread risk**: DOGE/DASH/ICP may have wider spreads than major crypto (monitor execution costs)

### Backtesting Targets (WF OOS)
- **Crypto**: Target Sharpe >1.5 (similar to BTCUSD +56%)
- **Commodities**: Target Sharpe >1.0 (NATGAS volatility → higher returns but drawdowns)
- **Forex**: Target Sharpe >0.8 (lower volatility, consistent returns)
- **Indices**: Target Sharpe >1.2 (NAS100 volatility higher than US500)

---

## 📚 Research Sources

### Cryptocurrency Research
- [Top 10 Cryptos To Invest In February 2026 | ZebPay](https://zebpay.com/blog/top-10-cryptos-to-invest-in-2026)
- [How Solana's $117B DEX volume overtook Ethereum in 2026](https://ambcrypto.com/how-solanas-117b-dex-volume-overtook-ethereum-in-2026/)
- [Solana Price: SOL Live Price Chart](https://www.coingecko.com/en/coins/solana)
- [Best Altcoins to Watch in 2026](https://crypto.com/en/market-updates/top-altcoins-to-watch-in-2026)

### Commodities Research
- [The Commodity Markets Outlook in eight charts](https://blogs.worldbank.org/en/developmenttalk/the-commodity-markets-outlook-in-eight-charts2)
- [Copper Outlook 2026: Institutional Rotation, Supply Deficits](https://www.investing.com/analysis/copper-outlook-2026-institutional-rotation-supply-deficits-technical-analysis-200673451)
- [Commodities in 2026: 10 Numbers to Watch From Power to Oil](https://about.bnef.com/insights/commodities/commodities-in-2026-10-numbers-to-watch-from-power-to-oil/)
- [Commodity Market Outlook: Trends Driving Optimism in 2026](https://www.morganstanley.com/im/en-lu/institutional-investor/insights/outlooks/trends-driving-optimism-in-2026.html)

### Forex Research
- [The Most Volatile Forex Currency Pairs in 2026 | LiteFinance](https://www.litefinance.org/blog/for-beginners/how-to-trade-currency/most-volatile-forex-currency-pairs/)
- [GBP/USD's 1.3700 Wall: Is the Pound's 2026 Winning Momentum Over?](https://www.investingcube.com/forex/gbp-usds-1-3700-wall-is-the-pounds-2026-winning-momentum-over/)
- [British Pound Outlook for 2026](https://www.fxempire.com/forecasts/article/british-pound-outlook-for-2026-1570306)

### Indices Research
- [NASDAQ 100 Forecast & Price Predictions 2026](https://naga.com/en/news-and-analysis/articles/nasdaq-100-price-prediction)
- [Trade to Watch 2026: Nasdaq 100 Correction Risk Before New Highs](https://www.forex.com/en/news-and-analysis/trade-to-watch-2026-nasdaq-100-correction-risk-before-new-highs/)
- [Indices 2026 outlook: Commodities | Bloomberg](https://www.bloomberg.com/professional/insights/markets/indices-2026-outlook-commodities/)

---

## 🚀 Next Steps

1. **User Review & Approval** - Confirm 12 EPICs selection and priority tiers
2. **Implement Tier 1 (6 assets)** - Start with highest priority EPICs
3. **Backtest Historical Data** - Download 6 months OHLC for all 12 EPICs
4. **Train ML Models** - Extend XGBoost to 21 total assets
5. **Paper Trade Validation** - 2 weeks on 3 high-priority assets
6. **Phase 12: Live Trading** - Deploy to Capital.com live account

---

**Document Version**: 1.0
**Last Updated**: 2026-02-14 19:46 CET
**Verification Status**: ✅ 100% Success (12/12 assets found on Capital.com)
