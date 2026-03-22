# MANTIS AI — PROMPT CONTRACT 04
## Sprint: Vision AI su Chart + RAG Pipeline
## Sorgente: `qrak/LLM_trader`

---

## 🎯 OBIETTIVO SPRINT

Aggiungere a MANTIS due capability avanzate di lettura del contesto:

1. **Vision AI**: generazione automatica di chart annotati e analisi visuale
   tramite modelli LLM multimodali — il sistema "vede" il grafico come farebbe
   un trader esperto.

2. **RAG Pipeline**: sistema di Retrieval-Augmented Generation che arricchisce
   il contesto degli agenti con notizie recenti, dati macro e informazioni
   on-chain, usando embedding semantici per trovare il contesto più rilevante.

---

## 📂 NAVIGAZIONE REPO SORGENTE

```bash
gh repo clone qrak/LLM_trader /tmp/source_repos/LLM_trader/
```

### File chiave da analizzare (in ordine):
```
LLM_trader/
├── src/
│   ├── chart/
│   │   ├── chart_generator.py       ← PRIORITÀ 1: generazione chart con indicatori
│   │   └── pattern_analyzer.py      ← PRIORITÀ 1: rilevamento pattern visuale
│   ├── analysis/
│   │   ├── technical_calculator.py  ← PRIORITÀ 2: calcolo indicatori
│   │   └── prompt_builder.py        ← PRIORITÀ 1: costruzione prompt con chart
│   ├── rag/
│   │   ├── news_aggregator.py       ← PRIORITÀ 1: aggregazione notizie
│   │   ├── context_builder.py       ← PRIORITÀ 1: costruzione contesto RAG
│   │   └── relevance_scorer.py      ← PRIORITÀ 2: scoring rilevanza
│   ├── models/
│   │   └── model_manager.py         ← PRIORITÀ 2: gestione provider LLM
│   └── config.py                    ← PRIORITÀ 2: configurazione
├── dashboard/                       ← PRIORITÀ 3: (ispirazione per Angular UI)
└── README.md
```

### Cosa estrarre:
1. **Pipeline di generazione chart** con overlay di indicatori (matplotlib/plotly)
2. **Pattern di prompt construction** per vision AI
3. **News aggregator con smart relevance scoring**
4. **RAG context builder** — come costruire il contesto da multiple sorgenti
5. **"Lead paragraph extraction"** per notizie (inverted pyramid)
6. **Architettura del model manager** con fallback tra provider

---

## 🏗️ TASK DI IMPLEMENTAZIONE

### Task 4.1 — Chart Generator
Crea `mantis/vision/chart_generator.py`:

```python
class MantisChartGenerator:
    """
    Genera chart annotati per l'analisi visuale.
    Ispirato a LLM_trader chart_generator.py
    
    Produce immagini PNG di alta qualità (800x600 o 1200x600)
    con overlay di indicatori tecnici principali.
    """
    
    def generate(self, 
                 ohlcv_df: pl.DataFrame,
                 timeframe: str,
                 config: ChartConfig) -> bytes:
        """
        Genera chart completo con:
        - Candlestick plot principale
        - EMA 20, EMA 50 overlay
        - Volume bars in subplot
        - RSI in subplot (con linee 30/70)
        - Bande di Bollinger overlay
        - Annotazioni automatiche: livelli chiave S/R
        - Marcatori: ultimi 5 segnali MANTIS (BUY/SELL con P&L se disponibile)
        - Indicazione regime di mercato (colore sfondo)
        
        Ritorna bytes PNG — pronti per essere inviati all'LLM vision.
        """
        ...
    
    def generate_multi_timeframe(self, 
                                  timeframes: list[str]) -> dict[str, bytes]:
        """
        Genera grid di chart per più timeframe (1m, 5m, 15m).
        Layout: 1x3 o 2x2 in base al numero di timeframe.
        """
        ...
    
    def _add_support_resistance(self, ax, df: pl.DataFrame):
        """
        Calcola e annota livelli S/R usando pivot points.
        Colora in verde (support) e rosso (resistance).
        """
        ...
    
    def _annotate_mantis_signals(self, ax, signals: list[FinalDecision]):
        """Overlay dei segnali MANTIS sul chart con triangoli BUY/SELL."""
        ...
```

**Librerie:** `matplotlib` + `mplfinance` (aggiungi a `requirements_evolution.txt`)

### Task 4.2 — Vision Analyzer
Crea `mantis/vision/vision_analyzer.py`:

```python
class MantisVisionAnalyzer:
    """
    Usa Claude claude-sonnet-4-20250514 con vision per analizzare chart generati.
    Ispirato al "Visual Cortex Analyst" di LLM_trader.
    
    NON usa Gemini o altri provider — usa Claude nativo (già integrato in MANTIS).
    """
    
    # System prompt specializzato per analisi tecnica visuale
    VISION_SYSTEM_PROMPT = """
    Sei un analista tecnico esperto specializzato in crypto trading, in particolare BTC/USDT.
    Analizza il chart fornito e produci un report strutturato in JSON con:
    - trend_direction: BULLISH | BEARISH | NEUTRAL | RANGING
    - key_patterns: lista di pattern candlestick/formazioni rilevate
    - support_levels: livelli di supporto visibili
    - resistance_levels: livelli di resistenza visibili
    - volume_analysis: "INCREASING" | "DECREASING" | "NEUTRAL" con note
    - momentum: "BUILDING" | "FADING" | "NEUTRAL"
    - timeframe_consistency: se multi-timeframe, coerenza tra TF
    - visual_confidence: float 0-1 (quanta confidenza hai nella lettura)
    - actionable_insight: stringa breve con l'insight principale
    
    Rispondi SOLO con JSON valido, nessun testo aggiuntivo.
    """
    
    def analyze_chart(self, chart_bytes: bytes, 
                      additional_context: str = "") -> VisionReport:
        """
        Invia il chart a Claude vision e ritorna VisionReport.
        
        Implementa:
        - Encoding base64 dell'immagine
        - Costruzione messaggio con image_url block
        - Parsing JSON della risposta
        - Fallback se parsing fallisce (return VisionReport con low confidence)
        """
        ...
    
    def analyze_multi_timeframe(self, charts: dict[str, bytes]) -> MTFVisionReport:
        """
        Analizza più timeframe e produce sintesi della coerenza inter-timeframe.
        Un trade è più affidabile se tutti i TF sono allineati.
        """
        ...
```

**Schema output:**
```python
class VisionReport(BaseModel):
    timestamp: datetime
    trend_direction: Literal["BULLISH", "BEARISH", "NEUTRAL", "RANGING"]
    key_patterns: list[str]
    support_levels: list[float]
    resistance_levels: list[float]
    volume_analysis: str
    momentum: Literal["BUILDING", "FADING", "NEUTRAL"]
    visual_confidence: float
    actionable_insight: str
    chart_hash: str  # hash PNG per deduplication
```

### Task 4.3 — News RAG Ingester
Crea `mantis/rag/news_ingester.py`:

```python
class MantisNewsIngester:
    """
    Aggrega e processa notizie da multiple sorgenti.
    Ispirato al News Aggregator di LLM_trader.
    
    Sorgenti (usa API già presenti nel SIL di MANTIS):
    - Finnhub news endpoint (già integrato)
    - Alpha Vantage news (già integrato)
    - StockTwits feed (già integrato)
    
    NON aggiungere nuove API key — riusa i feed SIL esistenti.
    """
    
    def ingest(self, symbol: str = "BTCUSD", 
               lookback_hours: int = 4) -> list[NewsItem]:
        """
        Fetcha e deduplicata notizie delle ultime N ore.
        Estrae lead paragraph per ogni articolo.
        """
        ...
    
    def extract_lead_paragraph(self, text: str) -> str:
        """
        Ispirato a LLM_trader: estrae il paragrafo principale seguendo
        la struttura "inverted pyramid" del giornalismo.
        Usa euristiche semplici (prime 2-3 frasi) + pulizia testo.
        """
        ...
    
    def score_relevance(self, item: NewsItem, 
                        context: MarketContext) -> float:
        """
        Scoring rilevanza ispirato a LLM_trader relevance_scorer.
        Considera:
        - Keyword density (BTC, Bitcoin, crypto, market, Fed, etc.)
        - Recency (news più recenti = score più alto)
        - Source credibility (whitelist di fonti affidabili)
        - Sentiment alignment (news positiva in trending up = alta rilevanza)
        """
        ...
```

### Task 4.4 — RAG Context Builder
Crea `mantis/rag/context_builder.py`:

```python
class MantisRAGContextBuilder:
    """
    Costruisce il contesto arricchito per gli agenti LLM.
    Ispirato a LLM_trader context_builder.py.
    
    Integra:
    1. Notizie recenti rilevanti (top 5 per relevance score)
    2. Dati macro da FRED (già nel SIL)
    3. COT data (già nel SIL) — open interest crypto
    4. Fear & Greed (già nel SIL)
    5. Memoria MANTIS (da Sprint 3 — pattern simili storici)
    
    Output: stringa di contesto strutturata, pronta per essere inserita
    nel prompt degli agenti LLM.
    """
    
    MAX_CONTEXT_TOKENS: int = 2000  # Non superare per mantenere il prompt efficiente
    
    def build(self, market_context: MarketContext,
              memory_context: MemoryContext) -> RAGContext:
        """
        Costruisce il contesto RAG completo.
        Ordina gli item per rilevanza e tronca a MAX_CONTEXT_TOKENS.
        """
        ...
    
    def _format_news_section(self, news: list[NewsItem]) -> str:
        """Formatta le notizie come bullet points concisi."""
        ...
    
    def _format_macro_section(self, sil_data: SILData) -> str:
        """Formatta i dati macro (FRED, COT, F&G) in sintesi leggibile."""
        ...
    
    def _format_memory_section(self, memory: MemoryContext) -> str:
        """
        Formatta il contesto di memoria per gli agenti:
        - Pattern simili storici (top 3)
        - Warning da episodi negativi
        - Win rate recente
        """
        ...
```

### Task 4.5 — Vector Store per RAG
Crea `mantis/rag/vector_store.py`:

```python
class MantisVectorStore:
    """
    Store vettoriale per il retrieval semantico nel RAG.
    Usa FAISS in-memory con snapshot su disco.
    
    Indicizza:
    - Notizie (ultimi 7 giorni)
    - Pattern storici dalla LTM (Sprint 3)
    - Playbook di strategie custom
    """
    
    def add_document(self, text: str, metadata: dict) -> str:
        """Aggiunge documento al vector store."""
        ...
    
    def search(self, query: str, top_k: int = 5, 
               filter_metadata: dict = None) -> list[SearchResult]:
        """Semantic search con filtri opzionali su metadata."""
        ...
    
    def save(self, path: Path):
        """Persiste l'indice FAISS su disco."""
        ...
    
    def load(self, path: Path):
        """Carica indice da disco."""
        ...
```

### Task 4.6 — Vision Agent per Sprint 1
Crea `mantis/vision/vision_agent.py`:

```python
class MantisVisionAgent(MantisBaseAgent):
    """
    Agente Vision che si integra nel MantisAgentOrchestrator (Sprint 1).
    Genera chart, li analizza con Claude Vision e produce VisionSignal.
    
    Ruolo nell'orchestrator: "VISUAL_ANALYST"
    Quando è utile: mercati ranging, breakout detection, pattern confirmation
    Quando skippare: in trending forte (evita latenza inutile)
    """
    
    def analyze(self, market_context: MarketContext) -> VisionSignal:
        chart = self._chart_generator.generate(market_context.ohlcv, ...)
        vision_report = self._vision_analyzer.analyze_chart(chart)
        rag_context = self._rag_builder.build(market_context, ...)
        return VisionSignal(
            vision_report=vision_report,
            rag_context=rag_context,
            chart_confidence=vision_report.visual_confidence
        )
```

### Task 4.7 — Aggiornamento Angular Frontend
Nel modulo Angular esistente di MANTIS, aggiungi:
- Endpoint FastAPI `GET /api/v1/chart/{symbol}/{timeframe}` → PNG
- Endpoint FastAPI `GET /api/v1/rag/context` → RAGContext JSON
- Componente Angular per visualizzazione chart inline (usa `<img>` con base64)
- Panel "Context Intelligence" con notizie recenti e RAG summary

---

## 🧪 TEST RICHIESTI

Crea `tests/test_vision.py` e `tests/test_rag.py`:
- Test chart generation produce PNG valido (size > 0, mime type corretto)
- Test vision analysis con mock Claude API → VisionReport parsato correttamente
- Test relevance scorer ordina correttamente notizie
- Test RAG context non supera MAX_CONTEXT_TOKENS
- Test vector store: add → search → trova (similarity > 0.7)

---

## ✅ CRITERI DI COMPLETAMENTO SPRINT 4

- [ ] `mantis/vision/` package completo
- [ ] `mantis/rag/` package completo  
- [ ] Chart generation funziona su dati BTC/USDT fixture
- [ ] Vision analyzer chiama Claude API e parsa risposta
- [ ] RAG pipeline integra tutti i feed SIL esistenti (no nuove API)
- [ ] `MantisVisionAgent` integrato nell'Orchestrator (Sprint 1)
- [ ] Endpoint FastAPI per chart e contesto RAG
- [ ] Test passano
- [ ] `requirements_evolution.txt`: `mplfinance`, `faiss-cpu` (se non da Sprint 3)

---

*Sprint 4 di 5 | Dipende da: Sprint 1, Sprint 3 | Blocca: nessuno*
