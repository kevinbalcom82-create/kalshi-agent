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
        self._init_arb_table()

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


    def _init_arb_table(self):
        with __import__('sqlite3').connect(self.db_path, timeout=30) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS arb_spreads (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, kalshi_ticker TEXT, poly_token TEXT, kalshi_ask TEXT, poly_bid TEXT, gross_spread TEXT, net_spread TEXT, is_profitable INTEGER, executed INTEGER DEFAULT 0)")
    def log_arb_spread(self, kalshi_ticker, poly_token, kalshi_ask, poly_bid, gross_spread, net_spread, is_profitable, executed=False):
        try:
            with __import__('sqlite3').connect(self.db_path, timeout=5) as conn:
                conn.execute("INSERT INTO arb_spreads (kalshi_ticker, poly_token, kalshi_ask, poly_bid, gross_spread, net_spread, is_profitable, executed) VALUES (?,?,?,?,?,?,?,?)", (kalshi_ticker, poly_token, str(kalshi_ask), str(poly_bid), str(gross_spread), str(net_spread), int(is_profitable), int(executed)))
        except Exception: pass

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
