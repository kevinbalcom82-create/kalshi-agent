"""
agent_logger.py
Kalshi Agent v3.0 — Centralized SQLite Logger
Single persistent connection in WAL mode with threading lock.
All tables initialized here — single source of truth for DB schema.

TABLES:
  events       — all log_event() calls (the system log)
  trade_orders — every order submitted to Kalshi
  signals      — every AI signal generated (feeds dashboard)
  arb_spreads  — every arbitrage spread scan result
"""
import sqlite3
import datetime
import json
import threading
from config import cfg


class AgentLogger:
    def __init__(self):
        self.db_path = cfg.DB_PATH
        self._lock   = threading.Lock()
        self._conn   = sqlite3.connect(
            self.db_path,
            check_same_thread = False,
            timeout           = 30
        )
        self._init_db()

    def _init_db(self):
        """Creates all tables in a single transaction at boot."""
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")

            # ── Events (system log) ────────────────────────────────────────
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  DATETIME,
                    level      TEXT,
                    event_type TEXT,
                    ticker     TEXT,
                    message    TEXT,
                    reasoning  TEXT
                )
            """)
            # Add reasoning column if upgrading from older schema
            try:
                self._conn.execute(
                    "ALTER TABLE events ADD COLUMN reasoning TEXT"
                )
            except sqlite3.OperationalError:
                pass

            # ── Trade Orders (execution ledger) ────────────────────────────
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_orders (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp    DATETIME,
                    ticker       TEXT,
                    order_id     TEXT,
                    side         TEXT,
                    contracts    INTEGER,
                    status       TEXT,
                    raw_response TEXT
                )
            """)

            # ── Signals (AI signal log — feeds dashboard) ──────────────────
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp               DATETIME,
                    ticker                  TEXT,
                    signal                  TEXT,
                    confidence              INTEGER,
                    suggested_entry_dollars TEXT,
                    risk_flag               TEXT,
                    edge_source             TEXT,
                    reasoning               TEXT,
                    audit_notes             TEXT,
                    outcome                 TEXT,
                    settled_value           TEXT
                )
            """)

            # ── Arb Spreads (arbitrage scan log — feeds /pnl command) ──────
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS arb_spreads (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
                    kalshi_ticker TEXT,
                    poly_token    TEXT,
                    kalshi_ask    TEXT,
                    poly_bid      TEXT,
                    gross_spread  TEXT,
                    net_spread    TEXT,
                    is_profitable INTEGER,
                    executed      INTEGER DEFAULT 0
                )
            """)

            self._conn.commit()

    # ── Public Logging Methods ─────────────────────────────────────────────

    def log_event(
        self,
        level:      str,
        event_type: str,
        ticker:     str,
        message:    str,
        reasoning:  str = None
    ):
        """Logs any system event. Prints to terminal and writes to SQLite."""
        timestamp = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO events "
                    "(timestamp, level, event_type, ticker, message, reasoning) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (timestamp, level, event_type, ticker, message, reasoning)
                )
                self._conn.commit()
        except sqlite3.OperationalError as e:
            print(f"⚠️ Database Busy: {e}")

        print(f"[{level}] [{event_type}] {ticker}: {message}")

    def log_order(
        self,
        ticker:       str,
        order_id:     str,
        side:         str,
        contracts:    int,
        status:       str,
        raw_response: dict
    ):
        """Permanent ledger entry for every order submitted to an exchange."""
        timestamp = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO trade_orders "
                    "(timestamp, ticker, order_id, side, contracts, "
                    "status, raw_response) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (timestamp, ticker, order_id, side, contracts,
                     status, json.dumps(raw_response))
                )
                self._conn.commit()
        except sqlite3.OperationalError as e:
            self.log_event(
                "CRITICAL", "DB_ORDER_LOG_FAIL", ticker,
                f"Could not save order {order_id}: {e}"
            )

    def log_signal(
        self,
        ticker:      str,
        signal:      str,
        confidence:  int,
        entry:       str,
        risk:        str,
        edge:        str,
        reasoning:   str,
        audit_notes: str = ""
    ):
        """Logs every AI signal for dashboard win rate analysis."""
        timestamp = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO signals "
                    "(timestamp, ticker, signal, confidence, "
                    "suggested_entry_dollars, risk_flag, edge_source, "
                    "reasoning, audit_notes, outcome, settled_value) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', '0')",
                    (timestamp, ticker, signal, confidence,
                     str(entry), risk, edge, reasoning, audit_notes)
                )
                self._conn.commit()
        except sqlite3.OperationalError as e:
            self.log_event(
                "CRITICAL", "DB_SIGNAL_LOG_FAIL", ticker,
                f"Could not save signal: {e}"
            )

    def log_arb_spread(
        self,
        kalshi_ticker: str,
        poly_token:    str,
        kalshi_ask,
        poly_bid,
        gross_spread,
        net_spread,
        is_profitable: bool,
        executed:      bool = False
    ):
        """
        Logs every arb spread scan result.
        is_profitable and executed stored as integers (SQLite has no bool).
        Called by arb_scanner.py every 30 seconds.
        """
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO arb_spreads "
                    "(kalshi_ticker, poly_token, kalshi_ask, poly_bid, "
                    "gross_spread, net_spread, is_profitable, executed) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        kalshi_ticker,
                        poly_token,
                        str(kalshi_ask),
                        str(poly_bid),
                        str(gross_spread),
                        str(net_spread),
                        int(is_profitable),
                        int(executed)
                    )
                )
                self._conn.commit()
        except Exception:
            pass  # Never let arb logging crash the scan loop


# Global singleton — imported everywhere as `from output.agent_logger import logger`
logger = AgentLogger()
