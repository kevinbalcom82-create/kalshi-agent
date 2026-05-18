import sqlite3
import datetime
import json
from config import cfg

class AgentLogger:
    def __init__(self):
        self.db_path = cfg.DB_PATH
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # General Events Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    level TEXT,
                    event_type TEXT,
                    ticker TEXT,
                    message TEXT,
                    reasoning TEXT
                )
            """)
            try:
                conn.execute("ALTER TABLE events ADD COLUMN reasoning TEXT")
            except sqlite3.OperationalError:
                pass 

            # NEW: Dedicated Order Ledger
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    ticker TEXT,
                    order_id TEXT,
                    side TEXT,
                    contracts INTEGER,
                    status TEXT,
                    raw_response TEXT
                )
            """)

    def log_event(self, level, event_type, ticker, message, reasoning=None):
        timestamp = datetime.datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute(
                    "INSERT INTO events (timestamp, level, event_type, ticker, message, reasoning) VALUES (?, ?, ?, ?, ?, ?)",
                    (timestamp, level, event_type, ticker, message, reasoning)
                )
        except sqlite3.OperationalError as e:
            print(f"⚠️ Database Busy: {e}")
            
        print(f"[{level}] [{event_type}] {ticker}: {message}")

    def log_order(self, ticker, order_id, side, contracts, status, raw_response):
        """Permanent ledger for executed trades."""
        timestamp = datetime.datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute(
                    "INSERT INTO trade_orders (timestamp, ticker, order_id, side, contracts, status, raw_response) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (timestamp, ticker, order_id, side, contracts, status, json.dumps(raw_response))
                )
        except sqlite3.OperationalError as e:
            logger.log_event("CRITICAL", "DB_ORDER_LOG_FAIL", ticker, f"Could not save order {order_id}: {e}")

logger = AgentLogger()
