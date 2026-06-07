"""
ghost_book.py
Kalshi Agent v3.0 — Paper Trading Ledger
Logs simulated trades to SQLite for performance tracking before going live.
Every signal the agent generates can be ghost-booked first — grade it WIN/LOSS
after settlement to build a verified track record.
"""
import sqlite3
import os
import time

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

try:
    from config import cfg
    DB_PATH = cfg.DB_PATH
except ImportError:
    DB_PATH = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")


def _ensure_table():
    """Creates the paper_trades table if it doesn't exist yet."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS paper_trades (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp               DATETIME DEFAULT CURRENT_TIMESTAMP,
            strategy                TEXT,
            ticker                  TEXT,
            signal                  TEXT,
            confidence              INTEGER,
            simulated_entry_price   TEXT,
            simulated_contracts     INTEGER,
            edge_source             TEXT,
            reasoning               TEXT,
            outcome                 TEXT DEFAULT 'PENDING',
            settled_value           TEXT
        )
    ''')
    conn.commit()
    conn.close()


def execute_paper_trade(
    strategy: str,
    ticker: str,
    signal: str,
    confidence: int,
    entry_price: str,
    contracts: int,
    edge_source: str,
    reasoning: str
) -> bool:
    """
    Logs a simulated trade to the ghost book.
    Outcome starts as PENDING — use backfill_outcomes.py to grade it.
    """
    try:
        _ensure_table()
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('''
            INSERT INTO paper_trades
            (strategy, ticker, signal, confidence, simulated_entry_price,
             simulated_contracts, edge_source, reasoning, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        ''', (strategy, ticker, signal, confidence,
              str(entry_price), contracts, edge_source, reasoning))
        conn.commit()
        conn.close()

        logger.log_event(
            "INFO", "GHOST_BOOK_EXECUTE", strategy,
            f"PAPER TRADE LOGGED: {contracts} contracts on {ticker} ({signal}) @ {entry_price}"
        )
        return True

    except Exception as e:
        logger.log_event("ERROR", "GHOST_BOOK_FAIL", strategy, str(e))
        return False


def get_paper_stats() -> dict:
    """
    Returns win rate and total paper PnL for the Telegram /status command.
    Useful for morning briefing and dashboard display.
    """
    try:
        _ensure_table()
        conn = sqlite3.connect(DB_PATH, timeout=5)
        cur  = conn.cursor()

        cur.execute("SELECT outcome FROM paper_trades WHERE outcome != 'PENDING'")
        outcomes = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT COUNT(*) FROM paper_trades WHERE outcome = 'PENDING'")
        pending = cur.fetchone()[0]

        conn.close()

        if not outcomes:
            return {"win_rate": 0.0, "total_graded": 0, "pending": pending}

        wins     = outcomes.count("WIN")
        win_rate = round((wins / len(outcomes)) * 100, 1)
        return {
            "win_rate":     win_rate,
            "total_graded": len(outcomes),
            "wins":         wins,
            "losses":       len(outcomes) - wins,
            "pending":      pending
        }

    except Exception as e:
        logger.log_event("ERROR", "GHOST_BOOK_STATS_FAIL", "SYSTEM", str(e))
        return {"win_rate": 0.0, "total_graded": 0, "pending": 0}
