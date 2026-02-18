# 🔍 Guida Debug SL/TP - Capital.com API

## Problema Riportato

L'utente ha segnalato che SL (Stop Loss) e TP (Take Profit) **non vengono inviati** a Capital.com API quando si apre una nuova posizione.

## Analisi Codice (COMPLETO ✅)

Il flusso è **CORRETTO** a livello di implementazione:

```
1. RiskManager.check()
   ├─ stop_loss = StopManager.calculate_stop_loss() [2x ATR]
   └─ take_profit = StopManager.calculate_take_profit() [2:1 R:R]

2. RiskCheckResult
   ├─ stop_loss: float
   └─ take_profit: float

3. ExecutionEngine.execute_signal()
   └─ ExecutionOrder(stop_loss, take_profit)

4. OrderManager._live_fill()
   └─ CreatePositionRequest(stop_level, profit_level)

5. CapitalComClient.create_position()
   └─ POST /api/v1/positions {stopLevel, profitLevel}
```

## Logging Aggiunto 📝

Ho aggiunto logging dettagliato in **4 punti critici**:

### 1. OrderManager (PRIMA di inviare)
```python
# backend/src/execution/order_manager.py:149
🎯 Sending to broker: XAUUSD BUY entry=2650.50 SL=2640.30 TP=2670.90
```

### 2. CapitalComClient (Payload API)
```python
# backend/src/broker/client.py:291
📤 Capital.com API payload: GOLD BUY size=0.1 stopLevel=2640.30 profitLevel=2670.90
```

### 3. CapitalComClient (Risposta broker)
```python
# backend/src/broker/client.py:303
📥 Broker response: dealId=ABC123 status=ACCEPTED level=2650.52 reason=OK
```

### 4. List Positions (Posizioni aperte)
```python
# backend/src/broker/client.py:383
📊 Position ABC123: GOLD BUY entry=2650.52 SL=2640.30 TP=2670.90
```

---

## Come Testare 🧪

### Step 1: Avvia Backend in DEMO Mode

```bash
cd backend
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --log-level debug
```

**IMPORTANTE**: Assicurati che il file `.env` contenga:
```bash
EXECUTION_MODE=DEMO  # NON PAPER!
CAPITAL_COM_API_KEY=your_demo_key
CAPITAL_COM_EMAIL=your_email
CAPITAL_COM_PASSWORD=your_demo_password
CAPITAL_COM_DEMO=true
```

### Step 2: Apri una Posizione

Via API:
```bash
curl -X POST http://localhost:8000/api/execution/execute \
  -H "Content-Type: application/json" \
  -d '{
    "epic": "XAUUSD",
    "direction": "BUY",
    "confidence": 0.75,
    "entry_price": 2650.00,
    "atr": 5.0
  }'
```

Oppure via Paper Trading Loop (avvia il loop e aspetta un segnale).

### Step 3: Controlla i Log

Cerca queste righe nel log (in ordine):

```
[INFO] 🎯 Sending to broker: XAUUSD BUY entry=2650.50 SL=??? TP=???
[INFO] 📤 Capital.com API payload: GOLD BUY size=0.1 stopLevel=??? profitLevel=???
[INFO] 📥 Broker response: dealId=ABC123 status=??? level=??? reason=???
[DEBUG] 📊 Position ABC123: GOLD BUY entry=2650.52 SL=??? TP=???
```

### Step 4: Verifica sul Broker

1. Apri Capital.com Demo Dashboard
2. Vai su "Posizioni Aperte"
3. Verifica se la posizione ha SL/TP impostati

---

## Possibili Scenari 🔍

### Scenario A: SL/TP sono NONE nei log
**Causa**: RiskManager non calcola i valori
**Soluzione**: Verifica che `signal.suggested_stop` e `signal.suggested_tp` non sovrascrivano con None

### Scenario B: SL/TP presenti nei log ma NONE nella posizione broker
**Causa**: Capital.com API rifiuta i valori (troppo vicini/lontani, formato errato)
**Soluzione**: Controlla `broker response: reason=???` per errori

### Scenario C: Payload API ha stopLevel=null
**Causa**: `model_dump(by_alias=True)` esclude campi None
**Soluzione**: Verifica se i valori sono None invece di float

### Scenario D: PAPER mode attivo
**Causa**: In PAPER mode non si invia nulla al broker
**Soluzione**: Cambia `EXECUTION_MODE=DEMO` in `.env`

---

## Comandi di Verifica Rapidi 🚀

```bash
# 1. Verifica modalità di esecuzione
curl http://localhost:8000/api/system/status | grep execution_mode

# 2. Controlla log in real-time
tail -f backend/logs/mantis-ai.log | grep "🎯\|📤\|📥\|📊"

# 3. Lista posizioni aperte
curl http://localhost:8000/api/execution/positions

# 4. Controlla ultimo segnale processato
curl http://localhost:8000/api/paper-trading/signals | head -n 50
```

---

## Fix Potenziali (Se Necessario) 🔧

### Fix 1: Garantire che SL/TP non siano mai None

Se il problema è che i valori sono None, potremmo aggiungere un fallback:

```python
# In OrderManager._live_fill()
request = CreatePositionRequest(
    epic=order.epic,
    direction=direction,
    size=order.size,
    stop_level=order.stop_loss if order.stop_loss and order.stop_loss > 0 else None,
    profit_level=order.take_profit if order.take_profit and order.take_profit > 0 else None,
)
```

### Fix 2: Usare stop_distance invece di stop_level

Se Capital.com richiede distanza in pips invece di prezzo assoluto:

```python
# Calcolare distanza
stop_distance = abs(order.entry_price - order.stop_loss) if order.stop_loss else None
profit_distance = abs(order.take_profit - order.entry_price) if order.take_profit else None

# Nota: CreatePositionRequest attualmente NON ha questi campi!
# Bisognerebbe aggiungerli se necessario.
```

### Fix 3: Validazione range SL/TP

Capital.com potrebbe rifiutare SL/TP troppo vicini (<1% dal prezzo):

```python
# Prima di inviare
min_distance_pct = 0.01  # 1%
entry = order.entry_price

if order.stop_loss:
    sl_distance_pct = abs(entry - order.stop_loss) / entry
    if sl_distance_pct < min_distance_pct:
        logger.warning(f"SL too close: {sl_distance_pct:.2%}, minimum 1%")
        # Aggiusta o rifiuta
```

---

## Prossimi Passi ⏭️

1. ✅ Logging aggiunto (FATTO)
2. ⏳ **Testare con DEMO mode** e verificare log
3. ⏳ Verificare posizioni su Capital.com Dashboard
4. ⏳ Applicare fix se necessario

---

## Riferimenti Codice 📚

- **RiskManager.check()**: [risk_manager.py:128-150](../backend/src/risk/risk_manager.py#L128-L150)
- **ExecutionEngine**: [execution_engine.py:64-71](../backend/src/execution/execution_engine.py#L64-L71)
- **OrderManager**: [order_manager.py:136-178](../backend/src/execution/order_manager.py#L136-L178)
- **CapitalComClient**: [client.py:277-316](../backend/src/broker/client.py#L277-L316)
- **CreatePositionRequest**: [models.py:125-134](../backend/src/broker/models.py#L125-L134)

---

**Autore**: Claude Sonnet 4.5
**Data**: 2026-02-15
**Issue**: SL/TP non inviati a Capital.com API
