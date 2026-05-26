import sqlite3, os

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

DB_PATH = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")

def execute_paper_trade(strategy, ticker, signal, confidence, entry_price, contracts, edge_source, reasoning):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('''
            INSERT INTO paper_trades 
            (ticker, signal, confidence, simulated_entry_price, simulated_contracts, edge_source, reasoning, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
        ''', (ticker, signal, confidence, entry_price, contracts, edge_source, reasoning))
        conn.commit()
        conn.close()
        
        # Log it to your terminal/Dashboard so you know it worked!
        logger.log_event("INFO", "GHOST_BOOK_EXECUTE", strategy, f"PAPER TRADE LOGGED: {contracts} contracts on {ticker} ({signal}) @ {entry_price}")
        return True
    except Exception as e:
        logger.log_event("ERROR", "GHOST_BOOK_FAIL", strategy, str(e))
        return False
