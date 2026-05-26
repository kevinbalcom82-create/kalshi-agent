import time
import os
import sqlite3
import sys
from datetime import datetime

# Add the root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import cfg
from output.agent_logger import logger
from data.yfinance_client import yfinance_client
from data.news_client import news_client
from engine.signal_engine import generate_signal

GHOST_DB_PATH = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")

# ==========================================
# 👻 GHOST BOOK INITIALIZATION
# ==========================================
def init_ghost_book():
    """Ensures the Ghost Book database and table exist."""
    os.makedirs(os.path.dirname(GHOST_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(GHOST_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS paper_trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  ticker TEXT,
                  signal TEXT,
                  confidence INTEGER,
                  outcome TEXT,
                  simulated_entry_price TEXT,
                  reasoning TEXT)''')
    conn.commit()
    conn.close()

def log_paper_trade(ticker, signal, confidence, price, reasoning):
    """Writes a simulated trade to the Ghost Book DB in WAL mode."""
    try:
        conn = sqlite3.connect(GHOST_DB_PATH, timeout=15)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("""INSERT INTO paper_trades 
                     (ticker, signal, confidence, outcome, simulated_entry_price, reasoning) 
                     VALUES (?, ?, ?, ?, ?, ?)""", 
                  (ticker, signal, confidence, "PENDING", str(price), reasoning))
        conn.commit()
        conn.close()
        logger.log_event("INFO", "PAPER_TRADE", ticker, f"Logged {signal} @ {price}")
    except Exception as e:
        logger.log_event("ERROR", "GHOST_BOOK_FAIL", ticker, str(e))

# ==========================================
# 🔄 CONTINUOUS HARVESTER LOOP
# ==========================================
def run_harvest_cycle():
    logger.log_event("INFO", "HARVESTER_BOOT", "SYSTEM", "Initializing macro data harvest.")

    # --- 1. DATA COLLECTION ---
    market_data = yfinance_client.get_market_context()
    spx_price = market_data.get("spx", {}).get("price", "UNKNOWN")
    vix_price = market_data.get("vix", {}).get("price", "UNKNOWN")
    
    news_data = news_client.get_sentiment("MACRO")
    
    # --- 2. AI SIGNAL GENERATION ---
    logger.log_event("INFO", "HERMES_BRAIN", "SPX_DAILY", "Analyzing VIX/SPX divergence for paper trade.")
    
    ai_prompt = (
        f"You are a quantitative macro analyst. "
        f"Current Market Data: S&P 500 is at {spx_price}, VIX is at {vix_price}. "
        f"News Sentiment Score is {news_data.get('sentiment_score', 0)}. "
        f"Based on this, generate a paper-trading signal for a daily equities market. "
        f"Provide a signal (BUY_YES, BUY_NO, WATCH), confidence (0-100), and short reasoning."
    )
    
    context = {
        "ticker": "SPX_DAILY",
        "prompt": ai_prompt
    }

    try:
        signal_output = generate_signal(context)
        
        sig = signal_output.get("signal", "UNKNOWN")
        conf = signal_output.get("confidence", 0)
        reason = signal_output.get("reasoning", "No reasoning provided.")
        
        # Log to Ghost Book instead of the funnel DB
        log_paper_trade("SPX_DAILY", sig, conf, spx_price, reason)
        
    except Exception as e:
        logger.log_event("ERROR", "SIGNAL_FAIL", "SPX_DAILY", f"Inference failed: {e}")

    logger.log_event("INFO", "HARVESTER_SLEEP", "SYSTEM", "Cycle complete. Sleeping 60m.")

if __name__ == "__main__":
    init_ghost_book()

    # The Continuous Loop
    while True:
        try:
            run_harvest_cycle()
        except Exception as e:
            logger.log_event("CRITICAL", "HARVESTER_FAULT", "SYSTEM", str(e))
        
        # Sleep for 1 Hour (3600 seconds)
        time.sleep(3600)
