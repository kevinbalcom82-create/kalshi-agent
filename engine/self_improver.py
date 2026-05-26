import sqlite3, json, time, threading, requests
from datetime import datetime, date
from config import cfg

try: from output.agent_logger import logger
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

OLLAMA_URL = "http://localhost:11434/api/chat"
AUDIT_MODEL = "deepseek-r1:8b"

def _get_db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def _fetch_unaudited_losses(conn: sqlite3.Connection, limit: int = 20) -> list:
    try:
        cursor = conn.execute("SELECT id, ticker, signal, confidence, suggested_entry_dollars, edge_source, reasoning, outcome, settled_value, timestamp FROM signals WHERE outcome = 'LOSS' AND (audit_notes IS NULL OR audit_notes NOT LIKE '%AUDITED%') ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.log_event("ERROR", "AUDITOR_FETCH_FAIL", "SYSTEM", str(e))
        return []

def _mark_as_audited(signal_id: int, lesson: str) -> None:
    try:
        conn = sqlite3.connect(cfg.DB_PATH, timeout=10)
        conn.execute("UPDATE signals SET audit_notes = ? WHERE id = ?", (f"AUDITED: {lesson[:200]}", signal_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.log_event("ERROR", "AUDITOR_MARK_FAIL", "SYSTEM", str(e))

def _extract_lesson(loss_trade: dict) -> str | None:
    prompt = f"You are a ruthless Quantitative Auditor.
A live capital trade just LOST money.
Your job is to extract one highly specific mechanical rule — with specific timeframes, spread thresholds, or data conditions.
Generic advice like 'be careful' is a failure.

## DETAILS\nTicker: {loss_trade['ticker']}\nSignal: {loss_trade['signal']}\nConfidence: {loss_trade['confidence']}%\nReasoning:\n{loss_trade['reasoning']}\n\nRespond ONLY with valid JSON:\n{{\n  \"root_cause\": \"...\",\n  \"lesson\": \"...\",\n  \"pattern_to_avoid\": \"...\"\n}}"
    try:
        payload = {"model": AUDIT_MODEL, "messages": [{"role": "system", "content": "You are a ruthless Quantitative Auditor. Extract highly specific mechanical rules. Output ONLY valid JSON."}, {"role": "user", "content": prompt}], "stream": False, "options": {"temperature": 0.3, "num_predict": 500}}
        response = requests.post(OLLAMA_URL, json=payload, timeout=120).json()
        raw_text = response.get("message", {}).get("content", "")
        if not raw_text.strip(): raw_text = response.get("message", {}).get("thinking", "")
        import re
        json_match = re.search(r'\{.*?\}', raw_text, re.DOTALL)
        if not json_match: return None
        data = json.loads(json_match.group(0))
        return f"ROOT CAUSE: {data.get('root_cause', '')} | AVOID: {data.get('lesson', '')} | PATTERN: {data.get('pattern_to_avoid', '')}"
    except Exception as e:
        logger.log_event("ERROR", "LESSON_EXTRACT_FAIL", "SYSTEM", str(e))
        return None

def run_nightly_audit() -> None:
    logger.log_event("INFO", "AUDIT_START", "SYSTEM", f"Nightly audit starting.")
    if not MEMORY_AVAILABLE: return
    conn = _get_db_conn()
    try:
        losses = _fetch_unaudited_losses(conn, limit=20)
        if not losses: return
        for trade in losses:
            try:
                lesson = _extract_lesson(trade)
                if not lesson: continue
                strategy_name = "SPORTS_SNIPER" if any(x in trade.get("ticker", "") for x in ["NBA","NFL","MLB"]) else "FOMC_WATCHER" if "FED" in trade.get("ticker", "") else "CPI_SNIPER" if "CPI" in trade.get("ticker", "") else "EQUITIES_HUNTER"
                inject_lesson(strategy_name, lesson, trade["id"])
                _mark_as_audited(trade["id"], lesson)
                time.sleep(2)
            except Exception: continue
        logger.log_event("INFO", "AUDIT_COMPLETE", "SYSTEM", "Audit done.")
    finally:
        conn.close()

def start_nightly_auditor() -> None:
    def _audit_loop():
        last_audit_date = None
        while True:
            now = datetime.now()
            if now.hour == 0 and now.minute < 30 and date.today() != last_audit_date:
                last_audit_date = date.today()
                try: run_nightly_audit()
                except Exception as e: logger.log_event("CRITICAL", "AUDIT_CRASH", "SYSTEM", str(e))
            time.sleep(300)
    threading.Thread(target=_audit_loop, daemon=True, name="NightlyAuditor").start()
    logger.log_event("INFO", "AUDITOR_ARMED", "SYSTEM", "Nightly auditor armed (fires at 00:00 ET).")
