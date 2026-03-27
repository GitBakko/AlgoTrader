"""
Telegram Bot command handler for MANTIS AI.

Polls for incoming messages and routes commands:
  /status  — Show trading status summary
  /reset   — Reset all circuit breakers
  /stop    — Emergency stop (close all positions)

Runs as a background task during app lifespan.
"""

import asyncio
from datetime import datetime, timezone

import httpx
from loguru import logger

from src.utils.config import get_settings

_TELEGRAM_API = "https://api.telegram.org"


class TelegramBotPoller:
    """Long-polling Telegram bot for interactive commands."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._offset = 0
        self._running = False
        self._task: asyncio.Task | None = None
        # Will be set from app state during startup
        self._get_loop = None  # callable that returns paper_loop

    @property
    def api_url(self) -> str:
        return f"{_TELEGRAM_API}/bot{self.bot_token}"

    async def send_message(self, text: str, chat_id: str | None = None) -> bool:
        """Send a message to a Telegram chat."""
        target = chat_id or self.chat_id
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={"chat_id": target, "text": text, "parse_mode": "Markdown"},
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    # Retry without Markdown
                    resp = await client.post(
                        f"{self.api_url}/sendMessage",
                        json={"chat_id": target, "text": text},
                        timeout=10.0,
                    )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def start(self):
        """Start the polling loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram bot poller started")

    async def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram bot poller stopped")

    async def _poll_loop(self):
        """Long-polling loop for Telegram updates."""
        while self._running:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{self.api_url}/getUpdates",
                        params={
                            "offset": self._offset,
                            "timeout": 30,
                            "allowed_updates": '["message"]',
                        },
                        timeout=40.0,
                    )
                    if resp.status_code != 200:
                        await asyncio.sleep(5)
                        continue

                    data = resp.json()
                    if not data.get("ok"):
                        await asyncio.sleep(5)
                        continue

                    for update in data.get("result", []):
                        self._offset = update["update_id"] + 1
                        await self._handle_update(update)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram poll error: {e}")
                await asyncio.sleep(10)

    async def _handle_update(self, update: dict):
        """Route incoming messages to command handlers."""
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Security: only respond to configured chat_id
        if chat_id != self.chat_id:
            logger.warning(f"Telegram: ignoring message from unauthorized chat {chat_id}")
            return

        if not text.startswith("/"):
            return

        cmd = text.split()[0].lower().split("@")[0]  # strip @botname

        if cmd == "/status":
            await self._cmd_status(chat_id)
        elif cmd == "/reset":
            await self._cmd_reset_cb(chat_id)
        elif cmd == "/stop":
            await self._cmd_emergency_stop(chat_id)
        elif cmd == "/help":
            await self._cmd_help(chat_id)
        else:
            await self.send_message(
                f"Comando sconosciuto: `{cmd}`\nUsa /help per la lista comandi.",
                chat_id,
            )

    async def _cmd_help(self, chat_id: str):
        await self.send_message(
            "*MANTIS AI Bot*\n\n"
            "/status — Stato trading\n"
            "/reset — Reset circuit breakers\n"
            "/stop — Emergency stop\n"
            "/help — Questo messaggio",
            chat_id,
        )

    async def _cmd_status(self, chat_id: str):
        loop = self._get_loop() if self._get_loop else None
        if loop is None:
            await self.send_message("Trading loop non attivo.", chat_id)
            return

        try:
            # Get live data from broker (source of truth)
            accounts = await loop.broker.get_accounts()
            account = accounts[0] if accounts else None
            equity = account.balance if account else 0
            broker_pnl = account.profit_loss if account else 0
            available = account.available if account else 0

            # Get open positions from broker
            positions = await loop.get_positions_async()
            pos_count = len(positions)

            # Position details
            pos_lines = []
            for p in positions:
                epic = p.get("epic", "?")
                direction = p.get("direction", "?")
                arrow = "▲" if direction == "BUY" else "▼"
                pos_lines.append(f"  {arrow} {epic} ({direction})")
            pos_text = "\n".join(pos_lines) if pos_lines else "  Nessuna"

            # Loop stats
            status = loop.get_status()
            is_running = status.get("running", False)
            iterations = status.get("iteration_count", 0)
            trades = status.get("trade_count", 0)
            errors = status.get("error_count", 0)
            eq_below = status.get("equity_curve_below_sma", False)

            # Win rate from closed trade history
            history = loop._trade_history or []
            if history:
                wins = sum(1 for t in history if t.get("pnl", 0) > 0)
                total = len(history)
                wr = (wins / total * 100) if total > 0 else 0
                wr_text = f"{wr:.1f}% ({wins}W/{total - wins}L su {total})"
            else:
                wr_text = "N/D"

            cb_tripped = status.get("circuit_breakers_tripped", {})
            cb_text = ""
            if cb_tripped:
                cb_lines = [f"  {k}: {v}" for k, v in cb_tripped.items()]
                cb_text = "\n\n*CB attivi:*\n" + "\n".join(cb_lines)

            # Epic SL cooldowns
            sl_cooldowns = status.get("epic_sl_cooldowns", {})
            sl_text = ""
            if sl_cooldowns:
                sl_lines = [
                    f"  {epic}: {count}/{loop._epic_sl_max_strikes} SL"
                    + (" BLOCCATO" if count >= loop._epic_sl_max_strikes else "")
                    for epic, count in sorted(sl_cooldowns.items(), key=lambda x: -x[1])
                ]
                sl_text = "\n\n*SL Cooldown (2h):*\n" + "\n".join(sl_lines)

            # Consecutive losses from CB
            consec = loop.risk_manager.circuit_breakers._consecutive_losses
            max_consec = loop.risk_manager.circuit_breakers.config.max_consecutive_losses

            pnl_sign = "+" if broker_pnl >= 0 else ""

            msg = (
                f"{'🟢' if is_running else '🔴'} *MANTIS AI Status*\n\n"
                f"*Equity:* ${equity:,.2f}\n"
                f"*P&L:* ${pnl_sign}{broker_pnl:.2f}\n"
                f"*Disponibile:* ${available:,.2f}\n\n"
                f"*Posizioni ({pos_count}):*\n{pos_text}\n\n"
                f"*Win Rate:* {wr_text}\n"
                f"*Consec. losses:* {consec}/{max_consec}\n"
                f"*Sessione:* {trades} trade, {iterations} iter, {errors} err\n"
                f"*Equity < SMA:* {'Si' if eq_below else 'No'}"
                f"{cb_text}{sl_text}"
            )
            await self.send_message(msg, chat_id)
        except Exception as e:
            logger.error(f"Telegram /status error: {e}")
            await self.send_message(f"Errore: {e}", chat_id)

    async def _cmd_reset_cb(self, chat_id: str):
        loop = self._get_loop() if self._get_loop else None
        if loop is None:
            await self.send_message("Trading loop non attivo.", chat_id)
            return

        try:
            reset_list = loop.risk_manager.circuit_breakers.reset_all()
            loop._per_asset_losses.clear()

            if reset_list:
                msg = f"Circuit breakers resettati ({len(reset_list)}):\n" + "\n".join(
                    f"  {b}" for b in reset_list
                )
            else:
                msg = "Nessun circuit breaker attivo da resettare."
            await self.send_message(msg, chat_id)
            logger.info(f"Telegram /reset: {len(reset_list)} breakers reset")
        except Exception as e:
            await self.send_message(f"Errore reset: {e}", chat_id)

    async def _cmd_emergency_stop(self, chat_id: str):
        loop = self._get_loop() if self._get_loop else None
        if loop is None:
            await self.send_message("Trading loop non attivo.", chat_id)
            return

        await self.send_message(
            "EMERGENCY STOP in corso...",
            chat_id,
        )

        try:
            result = await loop.emergency_stop()
            closed = result.get("positions_closed", 0)
            errors = result.get("errors", 0)
            await self.send_message(
                f"EMERGENCY STOP completato.\n" f"Posizioni chiuse: {closed}\n" f"Errori: {errors}",
                chat_id,
            )
        except Exception as e:
            await self.send_message(f"Errore emergency stop: {e}", chat_id)


# Singleton
_bot_poller: TelegramBotPoller | None = None


def get_telegram_bot() -> TelegramBotPoller | None:
    return _bot_poller


def init_telegram_bot() -> TelegramBotPoller | None:
    """Initialize the Telegram bot poller if configured."""
    global _bot_poller
    settings = get_settings()

    if not getattr(settings, "alert_telegram_enabled", False):
        return None

    bot_token = getattr(settings, "telegram_bot_token", "")
    chat_id = getattr(settings, "telegram_chat_id", "")
    if not bot_token or not chat_id:
        return None

    _bot_poller = TelegramBotPoller(bot_token=bot_token, chat_id=chat_id)
    return _bot_poller
