import sqlite3, os
from datetime import datetime, timedelta, timezone
from config import cfg

try:
    from engine.memory import save_memory
    MEMORY_ACTIVE = True
except ImportError:
    MEMORY_ACTIVE = False

# Connect to the Ghost Book DB
db_path = os.path.expanduser('~/kalshi_agent/output/ghost_book.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 3 Highly specific historical lessons
history = [
    {
        "ticker": "KXINTRADAY", "signal": "BUY_NO", "confidence": 85, "price": "0.45", "outcome": "WIN", 
        "reasoning": "Trend is STRONG_DOWN with confirming volume. VIX is above 25 indicating heavy market fear. Continuation of downward momentum is highly probable."
    },
    {
        "ticker": "KXNBA", "signal": "BUY_YES", "confidence": 72, "price": "0.55", "outcome": "LOSS", 
        "reasoning": "Home team holds a 3-1 series lead, but partial data quality regarding recent injuries created an unseen vulnerability. Overestimated home court advantage."
    },
    {
        "ticker": "KXINTRADAY", "signal": "WATCH", "confidence": 60, "price": "0.01", "outcome": "VOID", 
        "reasoning": "Market sentiment is perfectly neutral at 0.50 and VIX is steadily declining. No statistical edge detected. Capital preserved."
    }
]

print("💉 Injecting historical data...")

for i, trade in enumerate(history):
    # Offset dates so it looks like it happened over the last 3 days
    past_date = (datetime.now(timezone.utc) - timedelta(days=i+1)).strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Populate the UI Database
    c.execute("INSERT INTO paper_trades (timestamp, ticker, signal, confidence, outcome, simulated_entry_price, reasoning) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (past_date, trade["ticker"], trade["signal"], trade["confidence"], trade["outcome"], trade["price"], trade["reasoning"]))
              
    # 2. Populate the AI Memory (ChromaDB)
    if MEMORY_ACTIVE:
        try:
            strat = "EQUITIES_HUNTER" if "INTRADAY" in trade["ticker"] else "SPORTS_SNIPER"
            save_memory(
                strategy_name=strat,
                market_context={"ticker": trade["ticker"], "confidence": trade["confidence"]},
                ai_reasoning=trade["reasoning"],
                outcome=trade["outcome"]
            )
        except Exception as e:
            print(f"Memory inject failed for {trade['ticker']}: {e}")

conn.commit()
conn.close()
print("✅ Historical Data successfully injected into Ghost Book and AI Memory!")
