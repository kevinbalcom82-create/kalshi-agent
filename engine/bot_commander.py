import time
import requests
import threading
import sqlite3
import os
from config import cfg
from output.agent_logger import logger

class TelegramCommander:
    def __init__(self, pause_event):
        self.pause_event = pause_event
        self.last_update_id = 0
        self.boot_time = time.time()

    def _send_message(self, text):
        url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
        except Exception:
            pass

    def _get_status(self):
        uptime = int((time.time() - self.boot_time) / 60)
        try:
            with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                cur = conn.cursor()
                cur.execute("SELECT side, contracts, status FROM trade_orders ORDER BY id DESC LIMIT 1")
                last_trade = cur.fetchone()
        except Exception:
            last_trade = None
        
        state = "⏸ PAUSED (Pre-Warm Only)" if self.pause_event.is_set() else "▶️ ACTIVE (Live execution armed)"
        msg = f"📊 *Sniper Status*\nState: {state}\nUptime: {uptime} mins\nTarget: `{cfg.TARGET_TICKER}`\n"
        msg += f"Last Trade: {last_trade[0].upper()} x{last_trade[1]} ({last_trade[2]})" if last_trade else "Last Trade: None"
        return msg

    def _poll(self):
        url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/getUpdates"
        while True:
            try:
                resp = requests.get(url, params={"offset": self.last_update_id + 1, "timeout": 5}, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for result in data.get("result", []):
                        self.last_update_id = result["update_id"]
                        msg = result.get("message", {})
                        text = msg.get("text", "").strip().lower()
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        
                        if chat_id != str(cfg.TELEGRAM_CHAT_ID):
                            continue
                        
                        if text == "/pause":
                            self.pause_event.set()
                            self._send_message("⏸ *Sniper Paused.*\nAI will pre-warm, but live orders are BLOCKED.")
                            logger.log_event("WARNING", "REMOTE_COMMAND", "SYSTEM", "Sniper paused via Telegram.")
                        elif text == "/resume":
                            self.pause_event.clear()
                            self._send_message("▶️ *Sniper Resumed.*\nLive execution RE-ARMED.")
                            logger.log_event("INFO", "REMOTE_COMMAND", "SYSTEM", "Sniper resumed via Telegram.")
                        elif text == "/status":
                            self._send_message(self._get_status())
                        elif text == "/logs":
                            try:
                                log_path = os.path.expanduser("~/kalshi_agent/output/engine.log")
                                if not os.path.exists(log_path):
                                    self._send_message("⚠️ `engine.log` not found. System may just be booting.")
                                else:
                                    with open(log_path, "r", encoding="utf-8") as f:
                                        lines = f.readlines()[-15:]
                                        log_text = "".join(lines)[-3500:] # Telegram length limit safety
                                    self._send_message(f"🖥️ *Latest Engine Logs:*\n```text\n{log_text}\n```")
                            except Exception as e:
                                self._send_message(f"⚠️ Error reading logs: {e}")
                        elif text == "/positions":
                            try:
                                with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                                    cur = conn.cursor()
                                    cur.execute("SELECT ticker, side, contracts, status FROM trade_orders WHERE status != 'closed' ORDER BY id DESC LIMIT 5")
                                    rows = cur.fetchall()
                                    if not rows:
                                        self._send_message("📊 *Active Positions*\nNo open trades currently in database.")
                                    else:
                                        pos_msg = "📊 *Active Positions*\n"
                                        for r in rows:
                                            pos_msg += f"• `{r[0]}` | {r[1].upper()} x{r[2]} ({r[3]})\n"
                                        self._send_message(pos_msg)
                            except Exception as e:
                                self._send_message(f"❌ Database error: {e}")
                        elif text == "/balance":
                            self._send_message(f"💰 *Wallet Info*\nBankroll Allocated: ${cfg.BANKROLL}\n*(Live Kalshi API sync pending)*")
                        elif text == "/kelly":
                            self._send_message(f"💰 *Kelly Params*\nBankroll: ${cfg.BANKROLL}\nFormula: 1/4 Kelly\nMax Cap: 15%\nTarget: `{cfg.TARGET_TICKER}`")
                        elif text == "/pnl":
                            try:
                                with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                                    cursor = conn.execute("SELECT sum(net_spread), count(*) FROM arb_spreads WHERE executed = 1 AND timestamp >= datetime('now', '-1 day')")
                                    data_row = cursor.fetchone()
                                    total_profit = data_row[0] if data_row and data_row[0] else 0.00
                                    total_trades = data_row[1] if data_row and data_row[1] else 0
                                    self._send_message(f"📈 *Daily Alpha Report*\n\n💰 Net Profit: ${total_profit:.2f}\n🎯 Executed Trades: {total_trades}\n🤖 System Status: Nominal")
                            except Exception as e:
                                self._send_message(f"❌ Database error: {e}")
                        elif text in ["/panic", "/halt"]:
                            try:
                                self.pause_event.set() # Physically halts the engine!
                                with sqlite3.connect(cfg.DB_PATH, timeout=5) as conn:
                                    conn.execute("INSERT INTO system_logs (level, event_type, strategy, message) VALUES ('CRITICAL', 'PANIC_HALT', 'SYSTEM', 'User triggered /panic from Telegram. Engine locking down.')")
                                self._send_message("🛑 *ENGINE HALTED.*\nAll new executions have been suspended. Background loops are standing by for manual override.")
                                logger.log_event("CRITICAL", "REMOTE_COMMAND", "SYSTEM", "Engine halted via /panic.")
                            except Exception as e:
                                self._send_message(f"❌ Database error: {e}")
            except Exception:
                pass
            
            time.sleep(5)

def start_commander(pause_event):
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        return
    commander = TelegramCommander(pause_event)
    t = threading.Thread(target=commander._poll, daemon=True, name="TelegramCommander")
    t.start()
    logger.log_event("INFO", "COMMANDER_ONLINE", "SYSTEM", "Two-way Telegram listener active.")
