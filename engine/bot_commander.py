"""
bot_commander.py
Kalshi Agent v3.0 — Two-Way Telegram Command Center
Your remote control for the entire agent stack.

COMMANDS:
    /status     — Engine state, uptime, last trade
    /pause      — Block all live order execution
    /resume     — Re-arm live execution
    /logs       — Last 15 lines of agent logs from SQLite
    /positions  — Open trades in the database
    /balance    — Current bankroll config
    /kelly      — Kelly sizing parameters
    /pnl        — Daily arbitrage profit from signals table
    /panic      — Emergency halt + logs to database
    /halt       — Alias for /panic

Security: Only accepts commands from TELEGRAM_CHAT_ID in your .env
"""
import time
import requests
import threading
import sqlite3
from config import cfg
from output.agent_logger import logger


class TelegramCommander:
    def __init__(self, pause_event):
        self.pause_event     = pause_event
        self.last_update_id  = 0
        self.boot_time       = time.time()

    def _send_message(self, text: str):
        """Sends a message to your Telegram chat."""
        url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(
                url,
                json    = {
                    "chat_id":    cfg.TELEGRAM_CHAT_ID,
                    "text":       text,
                    "parse_mode": "Markdown"
                },
                timeout = 5
            )
        except Exception:
            pass

    def _get_status(self) -> str:
        """Builds the /status response from live DB data."""
        uptime = int((time.time() - self.boot_time) / 60)
        try:
            with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT side, contracts, status "
                    "FROM trade_orders ORDER BY id DESC LIMIT 1"
                )
                last_trade = cur.fetchone()
        except Exception:
            last_trade = None

        state = (
            "⏸ PAUSED (Pre-Warm Only)"
            if self.pause_event.is_set()
            else "▶️ ACTIVE (Live execution armed)"
        )
        msg = (
            f"📊 *Sniper Status*\n"
            f"State: {state}\n"
            f"Uptime: {uptime} mins\n"
            f"Target: `{cfg.TARGET_TICKER}`\n"
        )
        msg += (
            f"Last Trade: {last_trade[0].upper()} "
            f"x{last_trade[1]} ({last_trade[2]})"
            if last_trade else "Last Trade: None"
        )
        return msg

    def _get_recent_logs(self) -> str:
        """
        Pulls last 15 log events from SQLite events table.
        Does NOT rely on a log file path — works regardless of
        where the agent is launched from.
        """
        try:
            with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT timestamp, level, event_type, message "
                    "FROM events ORDER BY id DESC LIMIT 15"
                )
                rows = cur.fetchall()
                if not rows:
                    return "No log events found yet."

                lines = []
                for ts, level, event_type, message in reversed(rows):
                    ts_short = str(ts)[:19]
                    lines.append(f"[{level}] {event_type}: {message[:80]}")
                return "\n".join(lines)
        except Exception as e:
            return f"Log fetch error: {e}"

    def _get_pnl(self) -> str:
        """
        Daily PnL report from the signals table.
        Falls back gracefully if arb_spreads table doesn't exist yet.
        """
        try:
            with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                cursor = conn.cursor()

                # Try arb_spreads table first (populated when arb engine runs)
                try:
                    cursor.execute(
                        "SELECT SUM(net_spread), COUNT(*) "
                        "FROM arb_spreads "
                        "WHERE executed = 1 "
                        "AND timestamp >= datetime('now', '-1 day')"
                    )
                    row          = cursor.fetchone()
                    arb_profit   = round(row[0] or 0.0, 2)
                    arb_trades   = row[1] or 0
                except Exception:
                    arb_profit = 0.0
                    arb_trades = 0

                # Signal win rate from signals table (always available)
                cursor.execute(
                    "SELECT outcome, COUNT(*) "
                    "FROM signals "
                    "WHERE timestamp >= datetime('now', '-1 day') "
                    "GROUP BY outcome"
                )
                outcome_rows = cursor.fetchall()
                outcome_map  = {r[0]: r[1] for r in outcome_rows}
                wins         = outcome_map.get("WIN", 0)
                losses       = outcome_map.get("LOSS", 0)
                pending      = outcome_map.get("PENDING", 0)
                total_graded = wins + losses
                win_rate     = (
                    round((wins / total_graded) * 100, 1)
                    if total_graded > 0 else 0.0
                )

                return (
                    f"📈 *Daily Alpha Report*\n\n"
                    f"💰 Arb Net Profit: ${arb_profit:.2f} "
                    f"({arb_trades} executed)\n"
                    f"🎯 Signal Win Rate: {win_rate}% "
                    f"({wins}W / {losses}L / {pending} pending)\n"
                    f"🤖 System Status: Nominal"
                )

        except Exception as e:
            return f"❌ PnL fetch error: {e}"

    def _poll(self):
        """Main polling loop — checks for new Telegram commands every 5s."""
        url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/getUpdates"

        while True:
            try:
                resp = requests.get(
                    url,
                    params  = {"offset": self.last_update_id + 1, "timeout": 5},
                    timeout = 10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for result in data.get("result", []):
                        self.last_update_id = result["update_id"]
                        msg     = result.get("message", {})
                        text    = msg.get("text", "").strip().lower()
                        chat_id = str(msg.get("chat", {}).get("id", ""))

                        # Security gate — only accept from your chat ID
                        if chat_id != str(cfg.TELEGRAM_CHAT_ID):
                            continue

                        # ── Command Router ─────────────────────────────────
                        if text == "/pause":
                            self.pause_event.set()
                            self._send_message(
                                "⏸ *Sniper Paused.*\n"
                                "AI will pre-warm, but live orders are BLOCKED."
                            )
                            logger.log_event("WARNING", "REMOTE_COMMAND",
                                             "SYSTEM", "Sniper paused via Telegram.")

                        elif text == "/resume":
                            self.pause_event.clear()
                            self._send_message(
                                "▶️ *Sniper Resumed.*\nLive execution RE-ARMED."
                            )
                            logger.log_event("INFO", "REMOTE_COMMAND",
                                             "SYSTEM", "Sniper resumed via Telegram.")

                        elif text == "/status":
                            self._send_message(self._get_status())

                        elif text == "/logs":
                            log_text = self._get_recent_logs()
                            # Telegram has a 4096 char limit
                            self._send_message(
                                f"🖥️ *Latest Engine Logs:*\n"
                                f"```\n{log_text[-3500:]}\n```"
                            )

                        elif text == "/positions":
                            try:
                                with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                                    cur = conn.cursor()
                                    cur.execute(
                                        "SELECT ticker, side, contracts, status "
                                        "FROM trade_orders "
                                        "WHERE status != 'closed' "
                                        "ORDER BY id DESC LIMIT 5"
                                    )
                                    rows = cur.fetchall()
                                    if not rows:
                                        self._send_message(
                                            "📊 *Active Positions*\n"
                                            "No open trades currently."
                                        )
                                    else:
                                        pos_msg = "📊 *Active Positions*\n"
                                        for r in rows:
                                            pos_msg += (
                                                f"• `{r[0]}` | "
                                                f"{r[1].upper()} x{r[2]} ({r[3]})\n"
                                            )
                                        self._send_message(pos_msg)
                            except Exception as e:
                                self._send_message(f"❌ Database error: {e}")

                        elif text == "/balance":
                            self._send_message(
                                f"💰 *Wallet Info*\n"
                                f"Configured Bankroll: ${cfg.BANKROLL}\n"
                                f"Paper Trading: {getattr(cfg, 'PAPER_TRADING', True)}\n"
                                f"*(Live Kalshi balance sync pending)*"
                            )

                        elif text == "/kelly":
                            self._send_message(
                                f"💰 *Kelly Params*\n"
                                f"Bankroll: ${cfg.BANKROLL}\n"
                                f"Formula: 1/4 Kelly\n"
                                f"Max Cap: 15%\n"
                                f"Target: `{cfg.TARGET_TICKER}`"
                            )

                        elif text == "/pnl":
                            self._send_message(self._get_pnl())

                        elif text in ["/panic", "/halt"]:
                            self.pause_event.set()
                            try:
                                with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                                    conn.execute(
                                        "INSERT INTO events "
                                        "(level, event_type, ticker, message) "
                                        "VALUES (?, ?, ?, ?)",
                                        (
                                            "CRITICAL",
                                            "PANIC_HALT",
                                            "SYSTEM",
                                            "User triggered /panic from Telegram. "
                                            "Engine locking down."
                                        )
                                    )
                            except Exception:
                                pass
                            self._send_message(
                                "🛑 *ENGINE HALTED.*\n"
                                "All new executions suspended.\n"
                                "Send /resume to re-arm."
                            )
                            logger.log_event(
                                "CRITICAL", "REMOTE_COMMAND",
                                "SYSTEM", "Engine halted via /panic."
                            )

            except Exception:
                pass

            time.sleep(5)


def start_commander(pause_event):
    """
    Starts the Telegram command daemon thread.
    Call once from core_engine.py at boot.
    Returns immediately — runs in background forever.
    """
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        logger.log_event(
            "WARNING", "COMMANDER_SKIP", "SYSTEM",
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing — commander disabled."
        )
        return

    commander = TelegramCommander(pause_event)
    t = threading.Thread(
        target  = commander._poll,
        daemon  = True,
        name    = "TelegramCommander"
    )
    t.start()
    logger.log_event(
        "INFO", "COMMANDER_ONLINE", "SYSTEM",
        "Two-way Telegram listener active — all commands armed."
    )
