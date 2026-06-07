"""
self_improver.py
Kalshi Agent v3.0 — Nightly Audit & Learning Loop
Runs at midnight, audits every unreviewed WIN and LOSS trade,
extracts a mechanical lesson using hermes3:8b, and injects it
into ChromaDB vector memory so future trades learn from the past.

LOSS trades: "What went wrong? What rule prevents this?"
WIN trades:  "What worked? What conditions should we scale up?"

Starts automatically as a daemon thread via start_nightly_auditor().
"""
import sqlite3
import json
import time
import re
import threading
import requests
from datetime import datetime, date
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

try:
    from engine.memory import inject_lesson
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    def inject_lesson(*a, **kw): pass

OLLAMA_URL  = "http://localhost:11434/api/chat"
AUDIT_MODEL = "hermes3:8b"


def _get_db_conn() -> sqlite3.Connection:
    conn             = sqlite3.connect(cfg.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _detect_strategy(ticker: str) -> str:
    """
    Maps a ticker string to the correct strategy name for memory storage.
    Order matters — check most specific patterns first.
    """
    t = ticker.upper()
    if any(x in t for x in ["NBA", "NFL", "MLB"]):
        return "SPORTS_SNIPER"
    if any(x in t for x in ["FED", "FOMC", "KXFED"]):
        return "FOMC_WATCHER"
    if "INTRADAY" in t or "KXINTRADAY" in t:
        return "EQUITIES_HUNTER"
    if any(x in t for x in ["CPI", "KXCPI"]):
        return "CPI_SNIPER"
    if any(x in t for x in ["NFP", "KXNFP"]):
        return "NFP_SNIPER"
    # Default fallback
    return "CPI_SNIPER"


def _fetch_unaudited_trades(conn: sqlite3.Connection, limit: int = 20) -> list:
    """Fetches settled trades that haven't been audited yet."""
    try:
        cursor = conn.execute(
            "SELECT * FROM signals "
            "WHERE outcome IN ('WIN', 'LOSS') "
            "AND (audit_notes IS NULL OR audit_notes NOT LIKE '%AUDITED%') "
            "ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.log_event("ERROR", "AUDITOR_FETCH_FAIL", "SYSTEM", str(e))
        return []


def _mark_as_audited(signal_id: int, lesson: str) -> None:
    """Stamps the trade in SQLite so it won't be re-audited tomorrow."""
    try:
        conn = sqlite3.connect(cfg.DB_PATH, timeout=10)
        conn.execute(
            "UPDATE signals SET audit_notes = ? WHERE id = ?",
            (f"AUDITED: {lesson[:200]}", signal_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.log_event("ERROR", "AUDITOR_MARK_FAIL", "SYSTEM", str(e))


def _extract_lesson(trade: dict) -> str | None:
    """
    Sends the trade to hermes3:8b for post-mortem analysis.
    LOSS: extract the failure mode and prevention rule.
    WIN:  extract the edge pattern and scale-up conditions.
    """
    outcome = trade.get('outcome', 'UNKNOWN')

    if outcome == 'LOSS':
        prompt = (
            f"You are a ruthless Quantitative Auditor.\n"
            f"A live capital trade just LOST money.\n"
            f"Extract one highly specific mechanical rule to avoid this in the future.\n\n"
            f"## TRADE DETAILS\n"
            f"Ticker: {trade['ticker']}\n"
            f"Signal: {trade['signal']}\n"
            f"Confidence: {trade['confidence']}%\n"
            f"Reasoning:\n{trade['reasoning']}\n\n"
            f"Respond ONLY with valid JSON:\n"
            f"{{\n"
            f'  "root_cause": "...",\n'
            f'  "lesson": "...",\n'
            f'  "pattern_to_monitor": "..."\n'
            f"}}"
        )
    else:
        prompt = (
            f"You are an elite Quantitative Auditor.\n"
            f"A live capital trade just WON money and generated pure Alpha.\n"
            f"Extract the exact mechanical conditions that caused this win "
            f"so we can replicate and scale it.\n\n"
            f"## TRADE DETAILS\n"
            f"Ticker: {trade['ticker']}\n"
            f"Signal: {trade['signal']}\n"
            f"Confidence: {trade['confidence']}%\n"
            f"Reasoning:\n{trade['reasoning']}\n\n"
            f"Respond ONLY with valid JSON:\n"
            f"{{\n"
            f'  "root_cause": "...",\n'
            f'  "lesson": "...",\n'
            f'  "pattern_to_monitor": "..."\n'
            f"}}"
        )

    try:
        payload = {
            "model": AUDIT_MODEL,
            "messages": [
                {
                    "role":    "system",
                    "content": (
                        "You are a ruthless Quantitative Auditor. "
                        "Extract highly specific mechanical rules. "
                        "Output ONLY valid JSON."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "stream":  False,
            "options": {"temperature": 0.3, "num_predict": 500}
        }

        response = requests.post(
            OLLAMA_URL, json=payload, timeout=120
        ).json()

        raw_text = response.get("message", {}).get("content", "")
        if not raw_text.strip():
            raw_text = response.get("message", {}).get("thinking", "")

        json_match = re.search(r'\{.*?\}', raw_text, re.DOTALL)
        if not json_match:
            return None

        data = json.loads(json_match.group(0))
        return (
            f"ROOT CAUSE: {data.get('root_cause', '')} | "
            f"LESSON: {data.get('lesson', '')} | "
            f"PATTERN: {data.get('pattern_to_monitor', '')}"
        )

    except Exception as e:
        logger.log_event("ERROR", "LESSON_EXTRACT_FAIL", "SYSTEM", str(e))
        return None


def run_nightly_audit() -> None:
    """
    Main audit function — processes up to 20 unaudited trades per night.
    Sleeps 2 seconds between trades to avoid hammering Ollama.
    """
    logger.log_event("INFO", "AUDIT_START", "SYSTEM", "Nightly audit starting.")

    if not MEMORY_AVAILABLE:
        logger.log_event("WARNING", "AUDIT_SKIP", "SYSTEM",
                         "ChromaDB unavailable — install chromadb to enable memory.")
        return

    conn = _get_db_conn()
    try:
        trades = _fetch_unaudited_trades(conn, limit=20)
        if not trades:
            logger.log_event("INFO", "AUDIT_EMPTY", "SYSTEM",
                             "No unaudited trades found.")
            return

        for trade in trades:
            try:
                lesson = _extract_lesson(trade)
                if not lesson:
                    continue

                strategy_name = _detect_strategy(trade.get("ticker", ""))
                inject_lesson(strategy_name, lesson, trade["id"])
                _mark_as_audited(trade["id"], lesson)
                time.sleep(2)

            except Exception:
                continue

        logger.log_event("INFO", "AUDIT_COMPLETE", "SYSTEM",
                         f"Audit complete — {len(trades)} trades processed.")
    finally:
        conn.close()


def start_nightly_auditor() -> None:
    """
    Starts the daemon thread that fires run_nightly_audit() at midnight.
    Call this once from core_engine.py at boot — runs forever unattended.
    """
    def _audit_loop():
        last_audit_date = None
        while True:
            now = datetime.now()
            if (now.hour == 0 and
                    now.minute < 30 and
                    date.today() != last_audit_date):
                last_audit_date = date.today()
                try:
                    run_nightly_audit()
                except Exception as e:
                    logger.log_event("CRITICAL", "AUDIT_CRASH", "SYSTEM", str(e))
            time.sleep(300)  # Check every 5 minutes

    threading.Thread(
        target=_audit_loop,
        daemon=True,
        name="NightlyAuditor"
    ).start()
    logger.log_event("INFO", "AUDITOR_ARMED", "SYSTEM",
                     "Nightly auditor armed — fires at 00:00 ET.")
