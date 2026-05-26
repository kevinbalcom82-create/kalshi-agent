import sqlite3, requests, os
from datetime import datetime, timedelta, timezone
from config import cfg

try:
    from output.telegram_notifier import send_telegram
except ImportError:
    def send_telegram(msg): print(f"TELEGRAM: {msg}")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "hermes3:8b" 

def get_yesterdays_data():
    try:
        conn = sqlite3.connect(cfg.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Look back 24 hours
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 1. Fetch Real Trades
        cursor.execute("SELECT ticker, signal, confidence, outcome, settled_value FROM signals WHERE timestamp >= ?", (yesterday,))
        real_trades = [dict(r) for r in cursor.fetchall()]
        
        # 2. Fetch Paper Trades (Ghost Book)
        try:
            cursor.execute("SELECT ticker, signal, confidence, outcome FROM paper_trades WHERE timestamp >= ?", (yesterday,))
            paper_trades = [dict(r) for r in cursor.fetchall()]
        except:
            paper_trades = [] # Failsafe if Ghost Book is totally empty
            
        conn.close()
        return real_trades, paper_trades
    except Exception as e:
        print(f"Database error: {e}")
        return [], []

def generate_and_send_briefing():
    real, paper = get_yesterdays_data()
    
    if not real and not paper:
        send_telegram("☕ *Morning Briefing*\n\nNo trades were executed or simulated in the past 24 hours. The engine is idling, capital is preserved, and scanners are active for today's markets.")
        return

    context = f"REAL TRADES (USDC AT RISK):\n{real}\n\nPAPER TRADES (SIMULATED):\n{paper}\n"
    
    prompt = (
        "You are an elite quantitative portfolio manager. Write a concise, professional, 3-paragraph morning briefing for the fund owner (Kevin). "
        "Summarize the performance of the past 24 hours based ONLY on the provided JSON data. "
        "Paragraph 1: Executive summary of volume and outcomes. "
        "Paragraph 2: Breakdown of Real vs Paper trades (if any are 'PENDING', note they are awaiting market settlement). "
        "Paragraph 3: A brief forward-looking statement of system readiness. "
        "Output ONLY the text of the briefing. Use a highly professional, institutional tone. No markdown headers, just clean spacing."
    )

    try:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are a quantitative portfolio manager."},
                {"role": "user", "content": f"DATA:\n{context}\n\nINSTRUCTIONS:\n{prompt}"}
            ],
            "stream": False,
            "options": {"temperature": 0.3}
        }
        response = requests.post(OLLAMA_URL, json=payload, timeout=120).json()
        briefing = response.get("message", {}).get("content", "").strip()
        
        send_telegram(f"☕ *Morning Briefing*\n\n{briefing}")
    except Exception as e:
        send_telegram(f"⚠️ *Morning Briefing Error*\nFailed to generate AI summary: {e}")

if __name__ == "__main__":
    generate_and_send_briefing()
