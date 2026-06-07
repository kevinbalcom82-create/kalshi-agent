"""
morning_briefing.py
Kalshi Agent v3.0 — Daily Telegram Performance Report
Runs every morning, pulls last 24h of real and paper trades from SQLite,
feeds them to hermes3:8b locally, and sends a 3-paragraph institutional
briefing to your Telegram.

Paragraph 1: Executive summary of volume and outcomes
Paragraph 2: Real vs Paper trade breakdown
Paragraph 3: Forward-looking system readiness statement

Run standalone: python3 engine/morning_briefing.py
Or call generate_and_send_briefing() from your scheduler.
"""
import sqlite3
import requests
from datetime import datetime, timedelta, timezone
from config import cfg

try:
    from output.telegram_notifier import send_telegram as _send_telegram_orig

    def send_telegram(msg):
        try:
            _send_telegram_orig(msg)
        except Exception:
            pass
        return None

except ImportError:
    def send_telegram(msg):
        print(f"TELEGRAM: {msg}")
        return None

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "hermes3:8b"


def get_yesterdays_data():
    """Pulls last 24h of real trades and ghost book paper trades."""
    try:
        conn             = sqlite3.connect(cfg.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor           = conn.cursor()

        yesterday = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).strftime('%Y-%m-%d')

        # Real trades from signals table
        cursor.execute(
            "SELECT ticker, signal, confidence, outcome, settled_value "
            "FROM signals WHERE timestamp >= ?",
            (yesterday,)
        )
        real_trades = [dict(r) for r in cursor.fetchall()]

        # Paper trades from ghost book
        try:
            cursor.execute(
                "SELECT ticker, signal, confidence, outcome "
                "FROM paper_trades WHERE timestamp >= ?",
                (yesterday,)
            )
            paper_trades = [dict(r) for r in cursor.fetchall()]
        except Exception:
            paper_trades = []  # Ghost book empty or not yet initialized

        conn.close()
        return real_trades, paper_trades

    except Exception as e:
        print(f"Database error in morning_briefing: {e}")
        return [], []


def generate_and_send_briefing():
    """Main entry point — generates and sends the daily briefing."""
    real, paper = get_yesterdays_data()

    if not real and not paper:
        send_telegram(
            "☕ *Morning Briefing*\n\n"
            "No trades were executed or simulated in the past 24 hours. "
            "The engine is idling, capital is preserved, "
            "and scanners are active for today's markets."
        )
        return

    context = (
        f"REAL TRADES (CAPITAL AT RISK):\n{real}\n\n"
        f"PAPER TRADES (SIMULATED):\n{paper}\n"
    )

    prompt = (
        "You are an elite quantitative portfolio manager. "
        "Write a concise, professional, 3-paragraph morning briefing "
        "for the fund owner (Kevin). "
        "Summarize the performance of the past 24 hours based ONLY "
        "on the provided JSON data. "
        "Paragraph 1: Executive summary of volume and outcomes. "
        "Paragraph 2: Breakdown of Real vs Paper trades "
        "(if any are PENDING, note they are awaiting market settlement). "
        "Paragraph 3: A brief forward-looking statement of system readiness. "
        "Output ONLY the text of the briefing. "
        "Use a highly professional, institutional tone. "
        "No markdown headers, just clean paragraph spacing."
    )

    try:
        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role":    "system",
                    "content": "You are a quantitative portfolio manager."
                },
                {
                    "role":    "user",
                    "content": f"DATA:\n{context}\n\nINSTRUCTIONS:\n{prompt}"
                }
            ],
            "stream":  False,
            "options": {"temperature": 0.3}
        }

        response = requests.post(
            OLLAMA_URL, json=payload, timeout=120
        ).json()

        briefing = response.get("message", {}).get("content", "").strip()
        send_telegram(f"☕ *Morning Briefing*\n\n{briefing}")

    except Exception as e:
        send_telegram(
            f"⚠️ *Morning Briefing Error*\n"
            f"Failed to generate AI summary: {e}"
        )


if __name__ == "__main__":
    generate_and_send_briefing()
