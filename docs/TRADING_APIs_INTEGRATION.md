# TRADING APIs — Istruzioni di Integrazione

> **Questo file è un'istruzione operativa per Claude Code.**
> Contiene regole, architettura, codice Python (backend) e interfacce Angular (frontend) per integrare 4 API esterne nell'app di agentic algo trading.
> Seguire questo file nell'ordine indicato quando si implementano le integrazioni.

---

## REGOLE GLOBALI

### Env & Config

- Tutte le API key vanno in variabili d'ambiente. Mai hardcodate.
- Nomi variabili: `TAAPI_SECRET`, `TWELVEDATA_KEY`, `FINNHUB_KEY`, `MARKETAUX_TOKEN`
- Creare un file `config/api_keys.py`:

```python
import os

API_KEYS = {
    "taapi": os.environ["TAAPI_SECRET"],
    "twelvedata": os.environ["TWELVEDATA_KEY"],
    "finnhub": os.environ["FINNHUB_KEY"],
    "marketaux": os.environ["MARKETAUX_TOKEN"],
}
```

### Rate Limiting — Rispettare sempre questi limiti

| API | Max Freq | Max Giornaliero | Strategia |
|-----|----------|-----------------|-----------|
| TAAPI.IO | 1 req / 15 sec | Nessuno | Queue + sleep 15s tra chiamate |
| Twelve Data | 8 req / min | 800 / giorno | Token bucket, contatore giornaliero |
| Finnhub | 60 req / min | Nessuno | Semplice throttle 1 req/sec |
| Marketaux | — | 100 / giorno | Cache aggressiva, TTL 30 min |

### Regole di implementazione

1. **Ogni API va in un suo modulo Python separato** sotto `services/external/`
2. **Ogni modulo espone un'interfaccia uniforme** (vedi sezione Architettura)
3. **Retry con backoff esponenziale** su errori 429 (rate limit) e 5xx
4. **Timeout di 10 secondi** su ogni chiamata HTTP
5. **Logging strutturato** di ogni chiamata API (endpoint, symbol, latenza, status code)
6. **Cache in-memory con TTL** — i dati tecnici su TF >= 1h non servono freschi al millisecondo
7. **Fallback graceful** — se una API è down, l'agente opera con segnali parziali, mai crash
8. **Non lanciare eccezioni non gestite** — ogni chiamata API va in try/except, ritorna `None` o valore di default

---

## ARCHITETTURA

### Struttura file backend

```
backend/
├── config/
│   └── api_keys.py
├── services/
│   └── external/
│       ├── __init__.py
│       ├── base_client.py        # Client HTTP base con retry/timeout/logging
│       ├── taapi_client.py       # TAAPI.IO — indicatori tecnici bulk
│       ├── twelvedata_client.py  # Twelve Data — time series + indicatori
│       ├── finnhub_client.py     # Finnhub — news, insider, sentiment
│       ├── marketaux_client.py   # Marketaux — news sentiment per-ticker
│       └── signal_aggregator.py  # Combina segnali da tutte le API
├── models/
│   └── signals.py                # Dataclass per segnali strutturati
```

### Struttura Angular frontend (interfacce TypeScript)

```
frontend/src/app/
├── models/
│   ├── technical-signal.model.ts
│   ├── sentiment-signal.model.ts
│   └── composite-signal.model.ts
├── services/
│   └── signal.service.ts         # Chiama backend API
```

---

## MODULO BASE — `base_client.py`

Tutti i client API ereditano da questo. Implementa retry, timeout, logging, rate limiting.

```python
import time
import logging
import requests
from functools import wraps
from typing import Optional, Any

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter semplice basato su intervallo minimo tra chiamate."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last_call = 0.0

    def wait(self):
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()


class BaseAPIClient:
    """Client HTTP base con retry, timeout, logging e rate limiting."""

    BASE_URL: str = ""
    TIMEOUT: int = 10
    MAX_RETRIES: int = 3
    BACKOFF_FACTOR: float = 2.0

    def __init__(self, api_key: str, rate_limiter: Optional[RateLimiter] = None):
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.session = requests.Session()

    def _request(self, method: str, url: str, **kwargs) -> Optional[dict]:
        if self.rate_limiter:
            self.rate_limiter.wait()

        kwargs.setdefault("timeout", self.TIMEOUT)
        last_exc = None

        for attempt in range(self.MAX_RETRIES):
            try:
                start = time.time()
                resp = self.session.request(method, url, **kwargs)
                latency = round((time.time() - start) * 1000)

                logger.info(
                    "API call",
                    extra={
                        "client": self.__class__.__name__,
                        "url": url,
                        "status": resp.status_code,
                        "latency_ms": latency,
                    },
                )

                if resp.status_code == 429:
                    wait = self.BACKOFF_FACTOR ** (attempt + 1)
                    logger.warning(f"Rate limited, retry in {wait}s")
                    time.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    wait = self.BACKOFF_FACTOR ** (attempt + 1)
                    logger.warning(f"Server error {resp.status_code}, retry in {wait}s")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout (attempt {attempt + 1}/{self.MAX_RETRIES})")
                last_exc = "timeout"
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                last_exc = str(e)
                break

        logger.error(f"All retries exhausted: {last_exc}")
        return None

    def get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        url = f"{self.BASE_URL}/{endpoint}" if not endpoint.startswith("http") else endpoint
        return self._request("GET", url, params=params or {})

    def post(self, endpoint: str, json_data: dict = None) -> Optional[dict]:
        url = f"{self.BASE_URL}/{endpoint}" if not endpoint.startswith("http") else endpoint
        return self._request("POST", url, json=json_data or {})
```

---

## API 1 — TAAPI.IO (Indicatori Tecnici)

### Finalità nell'app

TAAPI.IO è il **motore di calcolo indicatori tecnici server-side**. Fornisce 208 indicatori pre-calcolati. L'agente non implementa algoritmi di TA: li richiede a TAAPI.IO e riceve valori numerici pronti per il decision engine. Il valore chiave è la **bulk query POST** che restituisce fino a 20 indicatori in una sola chiamata — essenziale per valutare condizioni multi-indicatore (es. `RSI < 30 AND MACD cross up AND price > EMA200`) con una singola richiesta.

### Docs di riferimento

- Documentazione: https://taapi.io/documentation/
- Lista completa 208 indicatori: https://taapi.io/indicators/
- Bulk query: https://taapi.io/documentation/integration/post-rest-bulk/
- Stocks: https://taapi.io/documentation/stocks/
- Manual (dati propri): https://taapi.io/documentation/integration/manually/

### `taapi_client.py`

```python
from typing import Optional
from services.external.base_client import BaseAPIClient, RateLimiter

# Indicatori standard per lo snapshot tecnico dell'agente.
# Modificare questa lista per aggiungere/rimuovere indicatori dal quadro decisionale.
DEFAULT_INDICATORS = [
    {"indicator": "rsi", "period": 14},
    {"indicator": "macd"},
    {"indicator": "ema", "period": 9, "id": "ema_9"},
    {"indicator": "ema", "period": 21, "id": "ema_21"},
    {"indicator": "ema", "period": 50, "id": "ema_50"},
    {"indicator": "ema", "period": 200, "id": "ema_200"},
    {"indicator": "bbands", "period": 20},
    {"indicator": "supertrend"},
    {"indicator": "stochrsi"},
    {"indicator": "atr", "period": 14},
    {"indicator": "adx"},
    {"indicator": "cci"},
    {"indicator": "obv"},
    {"indicator": "cmf"},
    {"indicator": "price"},
]


class TaapiClient(BaseAPIClient):
    """
    Client per TAAPI.IO — 208 indicatori tecnici.
    Free tier: 1 req/15s, bulk fino a 20 indicatori per request.
    """

    BASE_URL = "https://api.taapi.io"

    def __init__(self, api_key: str):
        # Free tier: 1 request ogni 15 secondi
        super().__init__(api_key, rate_limiter=RateLimiter(min_interval=15.0))

    def get_indicator(
        self,
        indicator: str,
        symbol: str,
        interval: str = "1d",
        asset_type: str = "stocks",
        **kwargs,
    ) -> Optional[dict]:
        """Singolo indicatore via GET. Usa bulk_snapshot per multi-indicatore."""
        params = {"secret": self.api_key, "symbol": symbol, "interval": interval}
        if asset_type == "stocks":
            params["type"] = "stocks"
        else:
            params["exchange"] = kwargs.get("exchange", "binance")
        params.update(kwargs)
        return self.get(indicator, params=params)

    def bulk_snapshot(
        self,
        symbol: str,
        interval: str = "1d",
        asset_type: str = "stocks",
        indicators: list[dict] = None,
        exchange: str = "binance",
    ) -> Optional[dict]:
        """
        Bulk query — fino a 20 indicatori in una POST.
        Questo è il metodo principale che l'agente deve usare.

        Args:
            symbol: Ticker (es. "AAPL" per stocks, "BTC/USDT" per crypto)
            interval: "1m","5m","15m","30m","1h","2h","4h","12h","1d","1w"
            asset_type: "stocks" o "crypto"
            indicators: Lista indicatori (default: DEFAULT_INDICATORS)
            exchange: Exchange per crypto (default: "binance")

        Returns:
            dict con chiave "data" contenente array di risultati per ogni indicatore.
            Ogni risultato ha: id, indicator, result (valori), errors.
            Ritorna None se la chiamata fallisce.
        """
        if indicators is None:
            indicators = DEFAULT_INDICATORS

        # Validazione: max 20 indicatori per bulk request
        if len(indicators) > 20:
            indicators = indicators[:20]

        construct = {"symbol": symbol, "interval": interval, "indicators": indicators}

        if asset_type == "stocks":
            construct["type"] = "stocks"
        else:
            construct["exchange"] = exchange

        payload = {"secret": self.api_key, "construct": construct}
        return self.post("bulk", json_data=payload)

    def bulk_with_own_candles(
        self, indicator: str, candles: list[dict], **params
    ) -> Optional[dict]:
        """
        Calcola un indicatore sui tuoi dati OHLCV.
        Utile quando hai già i dati dal tuo data provider.

        Args:
            indicator: Nome indicatore (es. "rsi", "macd")
            candles: Lista di dict con chiavi: open, high, low, close, volume
            **params: Parametri aggiuntivi dell'indicatore (es. period=14)
        """
        payload = {"secret": self.api_key, "candles": candles, **params}
        return self.post(indicator, json_data=payload)

    @staticmethod
    def parse_bulk_response(response: dict) -> dict:
        """
        Trasforma la risposta bulk in un dizionario piatto {indicator_id: result}.
        Utile per il decision engine dell'agente.
        """
        if not response or "data" not in response:
            return {}
        parsed = {}
        for item in response["data"]:
            key = item.get("id", item.get("indicator", "unknown"))
            if not item.get("errors"):
                parsed[key] = item.get("result", {})
        return parsed
```

### Endpoint Reference Rapido

| Azione | Metodo | Endpoint | Note |
|--------|--------|----------|------|
| Singolo indicatore | `GET` | `https://api.taapi.io/{indicator}` | Params: `secret`, `symbol`, `interval`, `type=stocks` |
| Bulk multi-indicatore | `POST` | `https://api.taapi.io/bulk` | JSON body con `construct` + `indicators[]`, max 20 |
| Calcolo su dati propri | `POST` | `https://api.taapi.io/{indicator}` | JSON body con `candles[]` (OHLCV) |
| Lista simboli | `GET` | `https://api.taapi.io/exchange-symbols` | Params: `secret`, `type=stocks` |

### Timeframe supportati

`1m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `12h`, `1d`, `1w`

### Struttura risposta bulk

```json
{
  "data": [
    {
      "id": "stocks_AAPL_1d_rsi_14_0",
      "indicator": "rsi",
      "result": { "value": 34.73 },
      "errors": []
    },
    {
      "id": "stocks_AAPL_1d_macd_0",
      "indicator": "macd",
      "result": {
        "valueMACD": -2.09,
        "valueMACDSignal": 0.05,
        "valueMACDHist": -2.15
      },
      "errors": []
    },
    {
      "id": "stocks_AAPL_1d_bbands_20_0",
      "indicator": "bbands",
      "result": {
        "valueUpperBand": 195.20,
        "valueMiddleBand": 188.50,
        "valueLowerBand": 181.80
      },
      "errors": []
    }
  ]
}
```

---

## API 2 — TWELVE DATA (Time Series + Indicatori)

### Finalità nell'app

Twelve Data fornisce **dati di prezzo OHLCV + indicatori tecnici nella stessa risposta**. Complementa TAAPI.IO: dove TAAPI.IO dà il valore corrente dell'indicatore, Twelve Data restituisce la **serie storica di prezzo con indicatori calcolati allineati temporalmente** — essenziale per backtesting, charting e costruzione dataset ML. Copre 100k+ simboli su 90+ exchange. Il free tier dà 800 chiamate/giorno — sufficiente per arricchire dati storici e analisi multi-asset. Il Python SDK permette di concatenare indicatori (`.with_rsi().with_macd()`), e il MCP server ufficiale consente ad agenti AI di interrogare l'API in linguaggio naturale.

### Docs di riferimento

- Documentazione: https://twelvedata.com/docs
- Python SDK: https://github.com/twelvedata/twelvedata-python (`pip install twelvedata`)
- MCP Server: https://github.com/twelvedata/mcp-server
- Lista indicatori: endpoint `GET /technical_indicators`

### `twelvedata_client.py`

```python
from typing import Optional
from services.external.base_client import BaseAPIClient, RateLimiter


class TwelveDataClient(BaseAPIClient):
    """
    Client per Twelve Data — time series OHLCV + 100+ indicatori tecnici.
    Free tier: 8 req/min, 800/giorno.
    """

    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: str):
        # Free tier: 8 req/min → ~1 ogni 7.5 sec
        super().__init__(api_key, rate_limiter=RateLimiter(min_interval=7.5))
        self._daily_count = 0
        self._daily_limit = 800

    def _check_daily_limit(self) -> bool:
        if self._daily_count >= self._daily_limit:
            import logging
            logging.getLogger(__name__).error("Twelve Data daily limit (800) reached")
            return False
        self._daily_count += 1
        return True

    def _params(self, **kwargs) -> dict:
        kwargs["apikey"] = self.api_key
        return kwargs

    def time_series(
        self,
        symbol: str,
        interval: str = "1day",
        outputsize: int = 50,
    ) -> Optional[dict]:
        """
        Serie storica OHLCV.

        Returns:
            dict con "meta" (info simbolo) e "values" (lista OHLCV per data).
        """
        if not self._check_daily_limit():
            return None
        return self.get("time_series", params=self._params(
            symbol=symbol, interval=interval, outputsize=outputsize
        ))

    def technical_indicator(
        self,
        indicator: str,
        symbol: str,
        interval: str = "1day",
        outputsize: int = 50,
        **kwargs,
    ) -> Optional[dict]:
        """
        Qualsiasi indicatore tecnico con serie storica.

        Args:
            indicator: Nome endpoint (es. "rsi", "macd", "bbands", "ema", "adx")
            symbol: Ticker
            interval: "1min","5min","15min","30min","45min","1h","2h","4h","8h","1day","1week","1month"
            outputsize: Numero data points (1-5000)
            **kwargs: Parametri specifici dell'indicatore (es. time_period=14, sd=2)
        """
        if not self._check_daily_limit():
            return None
        params = self._params(
            symbol=symbol, interval=interval, outputsize=outputsize, **kwargs
        )
        return self.get(indicator, params=params)

    def quote(self, symbol: str) -> Optional[dict]:
        """Prezzo corrente con dettagli (open, high, low, close, volume, change, ...)."""
        if not self._check_daily_limit():
            return None
        return self.get("quote", params=self._params(symbol=symbol))

    def price(self, symbol: str) -> Optional[dict]:
        """Solo il prezzo corrente — risposta minimale."""
        if not self._check_daily_limit():
            return None
        return self.get("price", params=self._params(symbol=symbol))

    def get_multi_indicator_series(
        self,
        symbol: str,
        interval: str = "1day",
        outputsize: int = 100,
        indicators: list[tuple[str, dict]] = None,
    ) -> dict:
        """
        Recupera time series + N indicatori in chiamate separate.
        Li allinea per timestamp nel risultato.
        ATTENZIONE: ogni indicatore costa 1 credito. Con 5 indicatori = 6 crediti totali.

        Args:
            indicators: Lista di (nome_indicatore, params_dict)
                        Es: [("rsi", {"time_period": 14}), ("macd", {}), ("bbands", {"sd": 2})]

        Returns:
            dict con "time_series" e un campo per ogni indicatore richiesto.
        """
        if indicators is None:
            indicators = [
                ("rsi", {"time_period": 14}),
                ("macd", {}),
                ("bbands", {"time_period": 20, "sd": 2}),
            ]

        result = {"time_series": self.time_series(symbol, interval, outputsize)}

        for ind_name, ind_params in indicators:
            result[ind_name] = self.technical_indicator(
                ind_name, symbol, interval, outputsize, **ind_params
            )

        return result
```

### Endpoint Reference Rapido

| Azione | Endpoint | Parametri chiave |
|--------|----------|------------------|
| Time series OHLCV | `GET /time_series` | `symbol`, `interval`, `outputsize` |
| Quote (prezzo dettaglio) | `GET /quote` | `symbol` |
| Price (prezzo semplice) | `GET /price` | `symbol` |
| RSI | `GET /rsi` | `symbol`, `interval`, `time_period` |
| MACD | `GET /macd` | `symbol`, `interval`, `fast_period`, `slow_period`, `signal_period` |
| Bollinger Bands | `GET /bbands` | `symbol`, `interval`, `time_period`, `sd`, `ma_type` |
| EMA | `GET /ema` | `symbol`, `interval`, `time_period` |
| ADX | `GET /adx` | `symbol`, `interval`, `time_period` |
| SuperTrend | `GET /supertrend` | `symbol`, `interval`, `multiplier`, `period` |
| Lista indicatori | `GET /technical_indicators` | — |

### Uso via Python SDK (alternativa al client custom)

```python
from twelvedata import TDClient

td = TDClient(apikey="YOUR_KEY")

# Concatenazione indicatori — singola chiamata logica, SDK gestisce le request
df = td.time_series(
    symbol="AAPL", interval="1day", outputsize=100
).with_rsi().with_macd().with_bbands().with_ema(time_period=50).as_pandas()

# df contiene: datetime, open, high, low, close, volume, rsi, macd, macd_signal, macd_hist,
#              upper_band, middle_band, lower_band, ema
```

---

## API 3 — FINNHUB (News + Insider + Alternative Data)

### Finalità nell'app

Finnhub è il layer di **intelligence non-tecnica**. Fornisce all'agente ciò che gli indicatori tecnici non possono catturare: comportamento degli insider, news in real-time, raccomandazioni analisti, earnings calendar, dati fondamentali. Il dato più prezioso è il **MSPR (Monthly Share Purchase Ratio)**: un indicatore da -100 a +100 che sintetizza se i dirigenti stanno comprando (+) o vendendo (-) azioni della propria azienda — segnale predittivo a 30-90 giorni. L'agente usa Finnhub per: confermare/invalidare segnali tecnici (es. non aprire long se insider vendono massicciamente), evitare posizioni prima di earnings, monitorare il consenso analisti. Il free tier è generoso (60 req/min) e include WebSocket per news e trade real-time.

### Docs di riferimento

- Documentazione: https://finnhub.io/docs/api
- Python SDK: `pip install finnhub-python`
- WebSocket: `wss://ws.finnhub.io?token=YOUR_TOKEN`

### `finnhub_client.py`

```python
from typing import Optional
from datetime import datetime, timedelta
from services.external.base_client import BaseAPIClient, RateLimiter


class FinnhubClient(BaseAPIClient):
    """
    Client per Finnhub — news, insider sentiment, alternative data.
    Free tier: 60 req/min.
    """

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str):
        # Free tier: 60 req/min → 1 req/sec
        super().__init__(api_key, rate_limiter=RateLimiter(min_interval=1.0))

    def _params(self, **kwargs) -> dict:
        kwargs["token"] = self.api_key
        return kwargs

    # ── NEWS ──────────────────────────────────────────────────

    def company_news(
        self, symbol: str, days_back: int = 7
    ) -> Optional[list]:
        """
        News recenti per un ticker.
        Returns: lista di dict con headline, summary, source, url, datetime.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        return self.get("company-news", params=self._params(
            symbol=symbol, **{"from": from_date, "to": today}
        ))

    def market_news(self, category: str = "general") -> Optional[list]:
        """News generali. Categorie: general, forex, crypto, merger."""
        return self.get("news", params=self._params(category=category))

    # ── INSIDER DATA ─────────────────────────────────────────

    def insider_sentiment(
        self, symbol: str, months_back: int = 12
    ) -> Optional[dict]:
        """
        MSPR (Monthly Share Purchase Ratio) — segnale insider.
        Valori: -100 (selling massiccio) a +100 (buying massiccio).
        Predittivo a 30-90 giorni.

        Returns:
            dict con "data" (lista mensile di {symbol, year, month, change, mspr})
        """
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=30 * months_back)).strftime("%Y-%m-%d")
        return self.get("stock/insider-sentiment", params=self._params(
            symbol=symbol, **{"from": from_date, "to": today}
        ))

    def insider_transactions(
        self, symbol: str, days_back: int = 90
    ) -> Optional[dict]:
        """
        Transazioni insider dettagliate (Form 3,4,5).
        Ogni transazione ha: name, change, transactionDate, transactionCode, transactionPrice.
        Codici: P=Purchase, S=Sale, A=Grant, M=Exercise options.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        return self.get("stock/insider-transactions", params=self._params(
            symbol=symbol, **{"from": from_date, "to": today}
        ))

    # ── ANALISTI & FONDAMENTALI ──────────────────────────────

    def recommendation_trends(self, symbol: str) -> Optional[list]:
        """Trend raccomandazioni analisti (strongBuy, buy, hold, sell, strongSell per mese)."""
        return self.get("stock/recommendation", params=self._params(symbol=symbol))

    def price_target(self, symbol: str) -> Optional[dict]:
        """Consenso price target analisti (targetHigh, targetLow, targetMean, targetMedian)."""
        return self.get("stock/price-target", params=self._params(symbol=symbol))

    def basic_financials(self, symbol: str) -> Optional[dict]:
        """
        Metriche fondamentali: P/E, 52wk high/low, market cap, margini, e centinaia di altre.
        """
        return self.get("stock/metric", params=self._params(symbol=symbol, metric="all"))

    def aggregate_indicators(self, symbol: str, resolution: str = "D") -> Optional[dict]:
        """
        Segnali tecnici aggregati da Finnhub (buy/sell/neutral).
        Basati su medie mobili e oscillatori.
        """
        return self.get("scan/technical-indicator", params=self._params(
            symbol=symbol, resolution=resolution
        ))

    # ── EARNINGS ─────────────────────────────────────────────

    def earnings_calendar(self, days_ahead: int = 7) -> Optional[dict]:
        """Prossimi earnings. Usare per evitare posizioni pre-earnings se la strategia lo richiede."""
        today = datetime.now().strftime("%Y-%m-%d")
        to_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        return self.get("calendar/earnings", params=self._params(
            **{"from": today, "to": to_date}
        ))

    # ── METODO AGGREGATO PER L'AGENTE ────────────────────────

    def get_full_context(self, symbol: str) -> dict:
        """
        Contesto completo non-tecnico per un ticker.
        Usato dall'agente per arricchire segnali tecnici con dati fondamentali e insider.
        Chiamata totale: ~7 request → ~7 secondi con rate limit.
        """
        return {
            "news": self.company_news(symbol, days_back=7),
            "insider_sentiment": self.insider_sentiment(symbol, months_back=6),
            "insider_transactions": self.insider_transactions(symbol, days_back=90),
            "recommendations": self.recommendation_trends(symbol),
            "price_target": self.price_target(symbol),
            "financials": self.basic_financials(symbol),
            "aggregate_signals": self.aggregate_indicators(symbol),
        }
```

### Endpoint Reference Rapido

| Azione | Endpoint | Note |
|--------|----------|------|
| News azienda | `GET /company-news` | Params: `symbol`, `from`, `to` |
| News mercato | `GET /news` | Params: `category` (general/forex/crypto/merger) |
| Insider sentiment (MSPR) | `GET /stock/insider-sentiment` | Params: `symbol`, `from`, `to` |
| Insider transactions | `GET /stock/insider-transactions` | Params: `symbol`, `from`, `to` |
| Raccomandazioni analisti | `GET /stock/recommendation` | Params: `symbol` |
| Price target consenso | `GET /stock/price-target` | Params: `symbol` |
| Fondamentali (P/E, mkt cap..) | `GET /stock/metric` | Params: `symbol`, `metric=all` |
| Segnali tecnici aggregati | `GET /scan/technical-indicator` | Params: `symbol`, `resolution` |
| Earnings calendar | `GET /calendar/earnings` | Params: `from`, `to` |
| WebSocket trades RT | `wss://ws.finnhub.io` | Subscribe con `{"type":"subscribe","symbol":"AAPL"}` |

### Struttura MSPR Response

```json
{
  "data": [
    { "symbol": "TSLA", "year": 2025, "month": 11, "change": 5540, "mspr": 12.20 },
    { "symbol": "TSLA", "year": 2025, "month": 12, "change": -1250, "mspr": -5.61 }
  ],
  "symbol": "TSLA"
}
```

- `change` > 0: insider stanno comprando (netto)
- `change` < 0: insider stanno vendendo (netto)
- `mspr` > 0: prevalenza acquisti, `mspr` < 0: prevalenza vendite

---

## API 4 — MARKETAUX (News Sentiment Per-Ticker)

### Finalità nell'app

Marketaux fornisce **sentiment analysis a livello di singola entità**. Un articolo che menziona 5 aziende produce 5 sentiment score separati, ciascuno con il passaggio di testo che lo ha generato. Questo è ciò che lo distingue da Finnhub: Finnhub dà news con sentiment generico a livello di articolo, Marketaux decompone il sentiment per ogni ticker menzionato. Per l'agente, questo significa poter rispondere a: "le news di oggi sono positive o negative per AAPL?" con un numero preciso, non un'opinione sull'intero articolo. Marketaux traccia 200k+ entità da 5k+ fonti in 30+ lingue. Il free tier (100 req/giorno, 3 articoli per richiesta) va usato con cache aggressiva e richieste mirate solo sui ticker sotto analisi attiva.

### Docs di riferimento

- Documentazione: https://www.marketaux.com/documentation
- Pricing/Free tier: https://www.marketaux.com/pricing

### `marketaux_client.py`

```python
from typing import Optional
from services.external.base_client import BaseAPIClient, RateLimiter


class MarketauxClient(BaseAPIClient):
    """
    Client per Marketaux — news con sentiment per-ticker.
    Free tier: 100 req/giorno, max 3 articoli per richiesta.
    """

    BASE_URL = "https://api.marketaux.com/v1"

    def __init__(self, api_key: str):
        # Nessun rate limit al secondo, ma 100/giorno → cache aggressiva
        super().__init__(api_key, rate_limiter=None)
        self._daily_count = 0
        self._daily_limit = 100

    def _check_daily_limit(self) -> bool:
        if self._daily_count >= self._daily_limit:
            import logging
            logging.getLogger(__name__).error("Marketaux daily limit (100) reached")
            return False
        self._daily_count += 1
        return True

    def get_news_sentiment(
        self,
        symbols: list[str],
        language: str = "en",
        limit: int = 3,
        published_after: str = None,
        must_have_entities: bool = True,
    ) -> Optional[dict]:
        """
        News con sentiment per-ticker.

        Args:
            symbols: Lista ticker (es. ["AAPL", "TSLA"])
            language: "en", "it", ecc.
            limit: Max articoli (free tier max 3)
            published_after: ISO datetime (es. "2026-02-13T00:00:00")
            must_have_entities: True per avere solo articoli con entità riconosciute

        Returns:
            dict con "meta" e "data" (lista articoli, ciascuno con "entities" contenente
            sentiment_score per-ticker e highlights con il testo rilevante)
        """
        if not self._check_daily_limit():
            return None

        params = {
            "api_token": self.api_key,
            "symbols": ",".join(symbols),
            "language": language,
            "filter_entities": "true",
            "limit": min(limit, 3),  # Free tier max 3
        }
        if must_have_entities:
            params["must_have_entities"] = "true"
        if published_after:
            params["published_after"] = published_after

        return self.get("news/all", params=params)

    def get_similar_news(self, uuid: str) -> Optional[dict]:
        """Trova articoli simili a uno specifico. Free tier: 3 req/giorno per questo endpoint."""
        if not self._check_daily_limit():
            return None
        return self.get(f"news/similar/{uuid}", params={"api_token": self.api_key})

    def extract_ticker_sentiments(self, response: dict) -> dict[str, dict]:
        """
        Estrae da una risposta Marketaux un dizionario:
        {
            "AAPL": {
                "avg_sentiment": 0.65,
                "article_count": 2,
                "latest_headline": "...",
                "highlights": ["testo positivo...", "altro testo..."]
            },
            "TSLA": { ... }
        }
        Usato dal signal_aggregator.
        """
        if not response or "data" not in response:
            return {}

        by_ticker: dict[str, dict] = {}

        for article in response["data"]:
            for entity in article.get("entities", []):
                sym = entity.get("symbol", "")
                score = entity.get("sentiment_score", 0)

                if sym not in by_ticker:
                    by_ticker[sym] = {
                        "scores": [],
                        "article_count": 0,
                        "headlines": [],
                        "highlights": [],
                    }

                by_ticker[sym]["scores"].append(score)
                by_ticker[sym]["article_count"] += 1
                by_ticker[sym]["headlines"].append(article.get("title", ""))

                for h in entity.get("highlights", []):
                    by_ticker[sym]["highlights"].append(h.get("highlight", ""))

        # Calcola medie
        for sym, data in by_ticker.items():
            scores = data.pop("scores")
            data["avg_sentiment"] = round(sum(scores) / len(scores), 4) if scores else 0
            data["latest_headline"] = data["headlines"][0] if data["headlines"] else ""

        return by_ticker
```

### Endpoint Reference Rapido

| Azione | Endpoint | Parametri chiave |
|--------|----------|------------------|
| News con sentiment | `GET /news/all` | `symbols`, `language`, `filter_entities`, `must_have_entities`, `published_after`, `sort`, `limit` |
| News simili | `GET /news/similar/{uuid}` | `api_token` |
| Entity stats | `GET /entity/stats/intraday` | `symbols`, `published_after`, `published_before` |

### Struttura risposta — focus su entities

```json
{
  "entities": [
    {
      "symbol": "AAPL",
      "name": "Apple Inc.",
      "type": "equity",
      "industry": "Technology",
      "match_score": 82.04,
      "sentiment_score": 0.7783,
      "highlights": [
        {
          "highlight": "Apple shares surged 5% after reporting...",
          "sentiment": 0.7783,
          "highlighted_in": "main_text"
        }
      ]
    }
  ]
}
```

- `sentiment_score`: da -1.0 (molto negativo) a +1.0 (molto positivo)
- `match_score`: quanto è rilevante l'entità nell'articolo (più alto = più centrale)
- `highlights`: i passaggi di testo che hanno generato il sentiment

---

## SIGNAL AGGREGATOR — `signal_aggregator.py`

Modulo che combina i dati delle 4 API in un segnale composito per l'agente.

```python
from dataclasses import dataclass, field
from typing import Optional
from services.external.taapi_client import TaapiClient
from services.external.twelvedata_client import TwelveDataClient
from services.external.finnhub_client import FinnhubClient
from services.external.marketaux_client import MarketauxClient


@dataclass
class TechnicalSignals:
    rsi: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_signal_cross: Optional[str] = None  # "bullish" | "bearish" | None
    price_vs_ema200: Optional[str] = None    # "above" | "below"
    supertrend_direction: Optional[str] = None  # "bullish" | "bearish"
    bollinger_position: Optional[str] = None    # "upper" | "middle" | "lower"
    adx_strength: Optional[float] = None
    atr: Optional[float] = None


@dataclass
class SentimentSignals:
    insider_mspr: Optional[float] = None          # -100 a +100
    insider_net_direction: Optional[str] = None    # "buying" | "selling" | "neutral"
    news_sentiment_avg: Optional[float] = None     # -1.0 a +1.0
    analyst_consensus: Optional[str] = None        # "strongBuy" | "buy" | "hold" | "sell"
    price_target_upside: Optional[float] = None    # % rispetto al prezzo corrente
    recent_news_count: int = 0


@dataclass
class CompositeSignal:
    symbol: str
    timestamp: str
    technical: TechnicalSignals = field(default_factory=TechnicalSignals)
    sentiment: SentimentSignals = field(default_factory=SentimentSignals)
    confidence: float = 0.0  # 0.0 a 1.0
    direction: Optional[str] = None  # "long" | "short" | "neutral"
    data_completeness: float = 0.0  # % di dati disponibili su quelli richiesti


class SignalAggregator:
    """
    Combina dati da TAAPI.IO, Twelve Data, Finnhub e Marketaux
    in un CompositeSignal usato dal decision engine dell'agente.
    """

    def __init__(
        self,
        taapi: TaapiClient,
        twelvedata: TwelveDataClient,
        finnhub: FinnhubClient,
        marketaux: MarketauxClient,
    ):
        self.taapi = taapi
        self.twelvedata = twelvedata
        self.finnhub = finnhub
        self.marketaux = marketaux

    def evaluate(self, symbol: str, interval: str = "1d") -> CompositeSignal:
        """
        Pipeline completo. Restituisce un CompositeSignal.
        Ordine chiamate (per priorità e velocità):
        1. TAAPI.IO bulk → quadro tecnico immediato
        2. Finnhub context → insider + news + analisti
        3. Marketaux → sentiment per-ticker granulare
        4. Twelve Data → solo se serve arricchimento storico
        """
        from datetime import datetime

        signal = CompositeSignal(
            symbol=symbol,
            timestamp=datetime.utcnow().isoformat(),
        )
        available_fields = 0
        total_fields = 10  # quanti dati ci aspettiamo

        # ── 1. TAAPI.IO — Indicatori tecnici ──────────────────
        bulk = self.taapi.bulk_snapshot(symbol, interval)
        if bulk:
            parsed = TaapiClient.parse_bulk_response(bulk)
            tech = signal.technical

            rsi_data = parsed.get("stocks_{s}_{i}_rsi_14_0".format(s=symbol, i=interval))
            if rsi_data:
                tech.rsi = rsi_data.get("value")
                available_fields += 1

            macd_data = parsed.get("stocks_{s}_{i}_macd_0".format(s=symbol, i=interval))
            if macd_data:
                tech.macd_histogram = macd_data.get("valueMACDHist")
                macd_val = macd_data.get("valueMACD", 0)
                macd_sig = macd_data.get("valueMACDSignal", 0)
                if macd_val and macd_sig:
                    tech.macd_signal_cross = "bullish" if macd_val > macd_sig else "bearish"
                available_fields += 1

            adx_data = parsed.get("stocks_{s}_{i}_adx_0".format(s=symbol, i=interval))
            if adx_data:
                tech.adx_strength = adx_data.get("value")
                available_fields += 1

            atr_data = parsed.get("stocks_{s}_{i}_atr_14_0".format(s=symbol, i=interval))
            if atr_data:
                tech.atr = atr_data.get("value")
                available_fields += 1

        # ── 2. FINNHUB — Insider + News + Analisti ─────────────
        context = self.finnhub.get_full_context(symbol)
        sent = signal.sentiment

        if context.get("insider_sentiment") and context["insider_sentiment"].get("data"):
            latest_mspr = context["insider_sentiment"]["data"][-1]
            sent.insider_mspr = latest_mspr.get("mspr")
            if sent.insider_mspr is not None:
                if sent.insider_mspr > 5:
                    sent.insider_net_direction = "buying"
                elif sent.insider_mspr < -5:
                    sent.insider_net_direction = "selling"
                else:
                    sent.insider_net_direction = "neutral"
            available_fields += 1

        if context.get("news"):
            sent.recent_news_count = len(context["news"])
            available_fields += 1

        if context.get("recommendations") and len(context["recommendations"]) > 0:
            latest = context["recommendations"][0]
            buy_total = latest.get("strongBuy", 0) + latest.get("buy", 0)
            sell_total = latest.get("strongSell", 0) + latest.get("sell", 0)
            if buy_total > sell_total * 2:
                sent.analyst_consensus = "strongBuy"
            elif buy_total > sell_total:
                sent.analyst_consensus = "buy"
            elif sell_total > buy_total:
                sent.analyst_consensus = "sell"
            else:
                sent.analyst_consensus = "hold"
            available_fields += 1

        if context.get("price_target") and context["price_target"].get("targetMean"):
            target_mean = context["price_target"]["targetMean"]
            # Per calcolare upside servirebbe il prezzo corrente
            # L'agente dovrà combinare con il prezzo dal proprio data provider
            sent.price_target_upside = target_mean
            available_fields += 1

        # ── 3. MARKETAUX — Sentiment per-ticker ────────────────
        maux_resp = self.marketaux.get_news_sentiment([symbol])
        if maux_resp:
            ticker_sentiments = self.marketaux.extract_ticker_sentiments(maux_resp)
            if symbol in ticker_sentiments:
                sent.news_sentiment_avg = ticker_sentiments[symbol]["avg_sentiment"]
                available_fields += 1

        # ── Calcolo confidence e direction ─────────────────────
        signal.data_completeness = round(available_fields / total_fields, 2)

        bullish_count = 0
        bearish_count = 0

        if signal.technical.rsi and signal.technical.rsi < 30:
            bullish_count += 1
        elif signal.technical.rsi and signal.technical.rsi > 70:
            bearish_count += 1

        if signal.technical.macd_signal_cross == "bullish":
            bullish_count += 1
        elif signal.technical.macd_signal_cross == "bearish":
            bearish_count += 1

        if sent.insider_net_direction == "buying":
            bullish_count += 1
        elif sent.insider_net_direction == "selling":
            bearish_count += 1

        if sent.news_sentiment_avg and sent.news_sentiment_avg > 0.3:
            bullish_count += 1
        elif sent.news_sentiment_avg and sent.news_sentiment_avg < -0.3:
            bearish_count += 1

        total_votes = bullish_count + bearish_count
        if total_votes > 0:
            signal.confidence = round(max(bullish_count, bearish_count) / total_votes, 2)
            signal.direction = "long" if bullish_count > bearish_count else "short"
        else:
            signal.direction = "neutral"

        return signal
```

---

## ANGULAR FRONTEND — Interfacce TypeScript

### `models/technical-signal.model.ts`

```typescript
export interface TechnicalSignals {
  rsi: number | null;
  macdHistogram: number | null;
  macdSignalCross: 'bullish' | 'bearish' | null;
  priceVsEma200: 'above' | 'below' | null;
  supertrendDirection: 'bullish' | 'bearish' | null;
  bollingerPosition: 'upper' | 'middle' | 'lower' | null;
  adxStrength: number | null;
  atr: number | null;
}
```

### `models/sentiment-signal.model.ts`

```typescript
export interface SentimentSignals {
  insiderMspr: number | null;
  insiderNetDirection: 'buying' | 'selling' | 'neutral' | null;
  newsSentimentAvg: number | null;
  analystConsensus: 'strongBuy' | 'buy' | 'hold' | 'sell' | null;
  priceTargetUpside: number | null;
  recentNewsCount: number;
}
```

### `models/composite-signal.model.ts`

```typescript
import { TechnicalSignals } from './technical-signal.model';
import { SentimentSignals } from './sentiment-signal.model';

export interface CompositeSignal {
  symbol: string;
  timestamp: string;
  technical: TechnicalSignals;
  sentiment: SentimentSignals;
  confidence: number;       // 0.0 — 1.0
  direction: 'long' | 'short' | 'neutral';
  dataCompleteness: number; // 0.0 — 1.0
}
```

### `services/signal.service.ts`

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { CompositeSignal } from '../models/composite-signal.model';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class SignalService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  getCompositeSignal(symbol: string, interval: string = '1d'): Observable<CompositeSignal> {
    return this.http.get<CompositeSignal>(
      `${this.baseUrl}/signals/composite`,
      { params: { symbol, interval } }
    );
  }

  getTechnicalSnapshot(symbol: string, interval: string = '1d'): Observable<any> {
    return this.http.get(
      `${this.baseUrl}/signals/technical`,
      { params: { symbol, interval } }
    );
  }

  getSentimentContext(symbol: string): Observable<any> {
    return this.http.get(
      `${this.baseUrl}/signals/sentiment`,
      { params: { symbol } }
    );
  }
}
```

---

## RIEPILOGO RAPIDO PER L'AGENTE

| Quando l'agente ha bisogno di... | Chiama... | Metodo |
|----------------------------------|-----------|--------|
| Quadro tecnico completo su un ticker | TAAPI.IO | `bulk_snapshot()` |
| Serie storica con indicatori per backtest/ML | Twelve Data | `get_multi_indicator_series()` |
| Insider stanno comprando o vendendo? | Finnhub | `insider_sentiment()` |
| News recenti e il loro tono per un ticker | Finnhub | `company_news()` |
| Sentiment numerico preciso per-ticker dalle news | Marketaux | `get_news_sentiment()` + `extract_ticker_sentiments()` |
| Consenso analisti e price target | Finnhub | `recommendation_trends()` + `price_target()` |
| Earnings in arrivo? (rischio evento) | Finnhub | `earnings_calendar()` |
| Segnale composito completo | SignalAggregator | `evaluate()` |

### Priorità chiamate per decisioni rapide

1. **TAAPI.IO** `bulk_snapshot()` — 1 chiamata, quadro tecnico in ~15 sec
2. **Finnhub** `insider_sentiment()` + `company_news()` — 2 chiamate, ~2 sec
3. **Marketaux** `get_news_sentiment()` — 1 chiamata, sentiment granulare
4. **Twelve Data** — solo quando serve storico/backtest, non per decisioni real-time
