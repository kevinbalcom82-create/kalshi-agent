import sqlite3
import datetime
import json
import threading
from config import cfg

class AgentLogger:
    def __init__(self):
        self.db_path = cfg.DB_PATH
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self._init_db()

    def _init_db(self):
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            
            self._conn.execute("""
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
                self._conn.execute("ALTER TABLE events ADD COLUMN reasoning TEXT")
            except sqlite3.OperationalError:
                pass 

            self._conn.execute("""
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

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    ticker TEXT,
                    signal TEXT,
                    confidence INTEGER,
                    suggested_entry_dollars TEXT,
                    risk_flag TEXT,
                    edge_source TEXT,
                    reasoning TEXT,
                    audit_notes TEXT,
                    outcome TEXT,
                    settled_value TEXT
                )
            """)
            self._conn.commit()

    def log_event(self, level, event_type, ticker, message, reasoning=None):
        timestamp = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO events (timestamp, level, event_type, ticker, message, reasoning) VALUES (?, ?, ?, ?, ?, ?)",
                    (timestamp, level, event_type, ticker, message, reasoning)
                )
                self._conn.commit()
        except sqlite3.OperationalError as e:
            print(f"⚠️ Database Busy: {e}")
            
        print(f"[{level}] [{event_type}] {ticker}: {message}")

    def log_order(self, ticker, order_id, side, contracts, status, raw_response):
        """Permanent ledger for executed trades."""
        timestamp = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO trade_orders (timestamp, ticker, order_id, side, contracts, status, raw_response) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (timestamp, ticker, order_id, side, contracts, status, json.dumps(raw_response))
                )
                self._conn.commit()
        except sqlite3.OperationalError as e:
            self.log_event("CRITICAL", "DB_ORDER_LOG_FAIL", ticker, f"Could not save order {order_id}: {e}")

    def log_signal(self, ticker, signal, confidence, entry, risk, edge, reasoning, audit_notes=""):
        """Logs AI reasoning so the Streamlit Dashboard can analyze win rates."""
        timestamp = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO signals (timestamp, ticker, signal, confidence, suggested_entry_dollars, risk_flag, edge_source, reasoning, audit_notes, outcome, settled_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', '0')",
                    (timestamp, ticker, signal, confidence, str(entry), risk, edge, reasoning, audit_notes)
                )
                self._conn.commit()
        except sqlite3.OperationalError as e:
            self.log_event("CRITICAL", "DB_SIGNAL_LOG_FAIL", ticker, f"Could not save signal: {e}")

logger = AgentLogger()
