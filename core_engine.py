"""
core_engine.py - Multi-Strat Execution Engine
Loads dynamic strategies, manages global execution locks, and handles Telegram C&C.
"""
import time
import schedule
import signal as os_signal
import sys
import threading
import requests
import os
from datetime import datetime
from decimal import Decimal
from config import cfg
from output.agent_logger import logger
from engine.bot_commander import start_commander
from engine.arb_scanner import start_arb_scanner
from engine.self_improver import start_nightly_auditor
from engine.morning_briefing import generate_and_send_briefing

# --- NEW: RAW BRAIN LOGGER ---
def log_raw_brain(ticker, strategy, input_prompt, raw_llm_response):
    """Dumps the unfiltered Ollama internal monologue to a secure log file."""
    log_path = os.path.expanduser("~/kalshi_agent/output/hermes_brain.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"🧠 HERMES RAW COGNITION | {timestamp} | {ticker}\n")
            f.write(f"STRATEGY: {strategy}\n")
            f.write(f"{'-'*60}\n")
            f.write(f"📥 INJECTED CONTEXT & MARKET DATA:\n{input_prompt}\n")
            f.write(f"{'-'*60}\n")
            f.write(f"📤 UNFILTERED AI OUTPUT (INTERNAL MONOLOGUE):\n{raw_llm_response}\n")
            f.write(f"{'='*60}\n")
    except Exception as e:
        logger.log_event("ERROR", "LOGGER_FAIL", "RAW_BRAIN", str(e))
# -----------------------------

# THE PAUSE FLAG (Thread-Safe)
SYSTEM_PAUSED = threading.Event()

# MULTI-STRAT CONCURRENCY LOCKS
EXECUTION_LOCK = threading.Lock()
_allocated = Decimal("0")
_allocation_lock = threading.Lock()

def reserve_capital(amount: Decimal) -> bool:
    with _allocation_lock:
        global _allocated
        cap = cfg.BANKROLL * Decimal("0.15") # 15% Max Global Cap
        if _allocated + amount > cap:
            return False
        _allocated += amount
        return True

def release_capital(amount: Decimal):
    with _allocation_lock:
        global _allocated
        _allocated = max(Decimal("0"), _allocated - amount)

def _shutdown(sig, frame):
    logger.log_event("INFO", "SHUTDOWN", "SYSTEM", f"Signal {sig} received. Commencing teardown.")
    close_fn = getattr(logger, "close", None)
    if callable(close_fn):
        close_fn()
    sys.exit(0)

os_signal.signal(os_signal.SIGTERM, _shutdown)
os_signal.signal(os_signal.SIGINT, _shutdown)

def _send_telegram_alert(message):
    print(f"🚨 TELEGRAM ALERT: {message}")
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": f"🤖 *Kalshi Multi-Strat:*\n{message}", "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.log_event("ERROR", "TELEGRAM_FAIL", "SYSTEM", str(e))

def _safe_pre_warm(strategy):
    try:
        strategy.pre_warm()
    except Exception as e:
        logger.log_event("CRITICAL", "PRE_WARM_CRASH", strategy.name, str(e))
        _send_telegram_alert(f"🚨 *{strategy.name} PRE_WARM CRASHED*\n{e}")

def _safe_execute(strategy):
    if SYSTEM_PAUSED.is_set():
        logger.log_event("WARNING", "STRIKE_ABORTED", strategy.name, "Engine is PAUSED. Strike aborted.")
        _send_telegram_alert(f"⚠️ *Strike Aborted* - Engine is PAUSED.\nStrategy: {strategy.name}")
        return
    try:
        strategy.execute(EXECUTION_LOCK, reserve_capital, release_capital)
    except Exception as e:
        logger.log_event("CRITICAL", "STRIKE_CRASH", strategy.name, str(e))
        _send_telegram_alert(f"🚨 *{strategy.name} STRIKE CRASHED*\n{e}")

def load_strategies():
    from strategies.cpi_sniper import CPISniper
    from strategies.nfp_sniper import NFPSniper
    from strategies.daily_equities import DailyEquitiesHunter
    from strategies.fomc_watcher import FOMCWatcher
    from strategies.sports_sniper import SportsSniperEdge
    return [CPISniper(), NFPSniper(), DailyEquitiesHunter(), FOMCWatcher(), SportsSniperEdge()]

def register_strategy(strategy):
    schedule.every().day.at(strategy.get_prewarm_time()).do(_safe_pre_warm, strategy)
    schedule.every().day.at(strategy.get_execute_time()).do(_safe_execute, strategy)
    logger.log_event("INFO", "STRATEGY_REGISTERED", strategy.name, f"Pre-warm: {strategy.get_prewarm_time()} | Execute: {strategy.get_execute_time()}")
    print(f"[+] Loaded: {strategy.name} (Trigger: {strategy.get_execute_time()})")

def start_scheduler():
    strategies = load_strategies()
    strat_names = [s.name for s in strategies]
    
    boot_msg = f"Live Mode Online.\nLoaded: {', '.join(strat_names)}"
    logger.log_event("INFO", "SYSTEM_BOOT", "SYSTEM", boot_msg)
    _send_telegram_alert(f"🟢 *System Boot*\n{boot_msg}")
    
    # Boot the 2-Way Telegram Listener
    start_commander(SYSTEM_PAUSED)
    
    # Boot the Nightly Auditor (Self-Improvement Loop)
    start_nightly_auditor()
    
    for s in strategies:
        register_strategy(s)

    if not getattr(cfg, "PAPER_TRADING", True):
        start_arb_scanner([s.ticker_prefix for s in strategies], reserve_capital, release_capital)
        
    schedule.every().day.at("08:00").do(generate_and_send_briefing)
    print(f"[*] Awaiting Schedule Triggers for {len(strategies)} active strategies...")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.log_event("CRITICAL", "SCHEDULER_LOOP_ERROR", "SYSTEM", str(e))
        time.sleep(1)

if __name__ == "__main__":
    start_scheduler()
