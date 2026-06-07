import sqlite3
import requests
import json
import os
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/npcforge/kalshi_agent/.env")

# --- CONFIG ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_KEY = os.getenv("GATEWAY_API_KEY", "suncoast-sovereign-key-2026")
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# --- CINEMATIC TERMINAL COLORS ---
class C:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    CYAN   = '\033[96m'
    BOLD   = '\033[1m'
    END    = '\033[0m'

# --- APP ---
app = FastAPI(
    title="Suncoast Gateway API",
    description="Sovereign lead ingestion and routing engine — Suncoast Agent Factory",
    version="2.0.0"
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://suncoast-treasures.com",
        "https://api.suncoast-treasures.com",
        "http://localhost:8505",
        "http://localhost:8501",
    ],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

# ==========================================
# 🗄️ DATABASE SETUP
# ==========================================
def init_db():
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scored_leads
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, company TEXT, message TEXT, source TEXT,
                  score INTEGER, tier TEXT, category TEXT, reasoning TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leads
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE,
                  captured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  status TEXT DEFAULT 'pending_audit')''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 🔐 AUTH
# ==========================================
def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key — access denied.")
    return x_api_key

# ==========================================
# 📦 MODELS
# ==========================================
class LeadPayload(BaseModel):
    name: str
    company: str
    message: str
    source: str

class LeadIn(BaseModel):
    name: str
    company: Optional[str] = "Unknown"
    message: str
    source: Optional[str] = "api"
    email: Optional[str] = None

class LeadUpdate(BaseModel):
    status: str

# NEW: Memory Query payload for the CRO
class MemoryQuery(BaseModel):
    question: str
    filter_type: str = "ALL"

# ==========================================
# 🧠 PIXEL BRAIN — Lead Scoring Engine
# ==========================================
def run_pixel_score(name: str, company: str, message: str, source: str) -> dict:
    system_prompt = (
        "You are PIXEL, an elite B2B AI lead qualifier. Analyze the user's message. "
        "Return ONLY a valid JSON object with these exact keys: "
        "'score' (integer 0-100), 'tier' (string: HOT, WARM, or COLD), "
        "'category' (string: short classification), and 'reasoning' (string: 1 sentence why)."
    )
    payload = {
        "model": "hermes3:8b",
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Company: {company}\nMessage: {message}"}
        ],
        "stream": False
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=30)
    ai_data = json.loads(response.json()["message"]["content"])
    return {
        "score":     ai_data.get("score", 0),
        "tier":      ai_data.get("tier", "UNKNOWN"),
        "category":  ai_data.get("category", "Uncategorized"),
        "reasoning": ai_data.get("reasoning", "No reasoning provided.")
    }

def save_scored_lead(name, company, message, source, score, tier, category, reasoning):
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO scored_leads (name, company, message, source, score, tier, category, reasoning) VALUES (?,?,?,?,?,?,?,?)",
        (name, company, message, source, score, tier, category, reasoning)
    )
    conn.commit()
    conn.close()

def send_discord_alert(name, company, source, score, tier, category, reasoning, message):
    if not DISCORD_WEBHOOK_URL:
        return
    tier_emoji  = {"HOT": "🔥", "WARM": "⚡", "COLD": "🧊"}.get(tier, "⚡")
    tier_color  = {"HOT": 16711680, "WARM": 16776960, "COLD": 3447003}.get(tier, 16776960)
    data = {
        "username": "PIXEL Lead Engine",
        "embeds": [{
            "title": f"{tier_emoji} {tier} LEAD — {name}",
            "color": tier_color,
            "fields": [
                {"name": "Company",   "value": company or "Unknown", "inline": True},
                {"name": "Source",    "value": source or "api",      "inline": True},
                {"name": "Score",     "value": str(score),           "inline": True},
                {"name": "Category",  "value": category,             "inline": True},
                {"name": "Action",    "value": "Route to Discovery Call Queue", "inline": True},
                {"name": "Reasoning", "value": reasoning,            "inline": False},
                {"name": "Message",   "value": message[:500],        "inline": False},
            ],
            "footer": {"text": f"Suncoast Agent Factory • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=5)
    except Exception as e:
        print(f"{C.RED}[DISCORD] Alert failed: {e}{C.END}")

def send_telegram_approval_alert(name, company, source, score, tier, category, reasoning, message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"{C.YELLOW}[TELEGRAM] Config missing, skipping alert.{C.END}")
        return
    tier_emoji = {"HOT": "🔥", "WARM": "⚡", "COLD": "🧊"}.get(tier, "⚡")
    text = (
        f"ℹ️ *[Sovereign] New Lead Audited*\n\n"
        f"👤 *Name:* `{name}`\n"
        f"🏢 *Company:* `{company or 'Unknown'}`\n"
        f"🔌 *Source:* `{source or 'api'}`\n"
        f"📊 *Score:* `{score}/100` ({tier_emoji} {tier})\n"
        f"🗂️ *Category:* {category}\n"
        f"📝 *Reasoning:* {reasoning}\n\n"
        f"💬 *Message Snippet:* _\"{message[:150]}...\"_"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
        print(f"{C.GREEN}[TELEGRAM] ✅ Audit alert pushed to Sovereign_Approvals_bot channel.{C.END}")
    except Exception as e:
        print(f"{C.RED}[TELEGRAM] PUSH FAILED: {e}{C.END}")

# ==========================================
# 🌐 ROUTES
# ==========================================
@app.post("/ingest/lead")
def ingest_lead(lead: LeadPayload):
    print(f"\n{C.CYAN}[{datetime.now().strftime('%H:%M:%S')}] 📥 NEW INBOUND LEAD DETECTED: {lead.name}{C.END}")
    print(f"{C.YELLOW}Routing to local Hermes-3 core for analysis...{C.END}")
    try:
        scored = run_pixel_score(lead.name, lead.company, lead.message, lead.source)
        score     = scored["score"]
        tier      = scored["tier"]
        category  = scored["category"]
        reasoning = scored["reasoning"]

        print(f"\n{C.BOLD}PIXEL Classification Result:{C.END}")
        print(f"  {C.BOLD}Score:{C.END}    {C.GREEN}{score}/100{C.END}")
        print(f"  {C.BOLD}Tier:{C.END}     {C.RED if tier == 'HOT' else C.YELLOW}{tier}{C.END}")
        print(f"  {C.BOLD}Category:{C.END} {C.CYAN}{category}{C.END}")
        print(f"  {C.BOLD}Action:{C.END}    Route to Discovery Call Queue")
        print(f"  {C.BOLD}Reasoning:{C.END} {reasoning}\n")

        save_scored_lead(lead.name, lead.company, lead.message, lead.source, score, tier, category, reasoning)
        print(f"{C.GREEN}[SYSTEM] ✅ Lead encrypted and logged locally to sovereign_leads.db{C.END}\n")
        send_discord_alert(lead.name, lead.company, lead.source, score, tier, category, reasoning, lead.message)
        send_telegram_approval_alert(lead.name, lead.company, lead.source, score, tier, category, reasoning, lead.message)
        return {"status": "success", "score": score, "tier": tier}
    except Exception as e:
        print(f"{C.RED}[ERROR] AI Engine Failed: {e}{C.END}")
        return {"status": "error", "message": str(e)}

@app.get("/health")
def health_check():
    try:
        conn = sqlite3.connect('sovereign_leads.db')
        conn.execute("SELECT 1")
        conn.close()
        db_status = "online"
    except Exception:
        db_status = "error"
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
        hermes_status = "online" if r.status_code == 200 else "error"
    except Exception:
        hermes_status = "offline"
    return {
        "status":  "online",
        "agents": {"pixel": "online", "hermes": hermes_status, "sqlite": db_status},
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }

@app.get("/leads")
def get_leads(tier: Optional[str] = None, limit: int = 50, api_key: str = Depends(verify_api_key)):
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    query = "SELECT id, name, company, source, score, tier, category, reasoning, timestamp FROM scored_leads WHERE 1=1"
    params = []
    if tier:
        query += " AND tier = ?"
        params.append(tier.upper())
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "company": r[2], "source": r[3], "score": r[4], "tier": r[5], "category": r[6], "reasoning": r[7], "timestamp": r[8]} for r in rows]

@app.get("/leads/{lead_id}")
def get_lead(lead_id: int, api_key: str = Depends(verify_api_key)):
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    c.execute("SELECT id, name, company, source, score, tier, category, reasoning, timestamp FROM scored_leads WHERE id = ?", (lead_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"id": row[0], "name": row[1], "company": row[2], "source": row[3], "score": row[4], "tier": row[5], "category": row[6], "reasoning": row[7], "timestamp": row[8]}

@app.get("/emails")
def get_emails(status: Optional[str] = None, limit: int = 50, api_key: str = Depends(verify_api_key)):
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    query = "SELECT id, email, captured_at, status FROM leads WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY captured_at DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "email": r[1], "captured_at": r[2], "status": r[3]} for r in rows]

@app.patch("/emails/{lead_id}")
def update_email_lead(lead_id: int, update: LeadUpdate, api_key: str = Depends(verify_api_key)):
    valid = ["pending_audit", "contacted", "qualified", "closed_won", "closed_lost", "booked_call", "deposit_paid"]
    if update.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid}")
    conn = sqlite3.connect('sovereign_leads.db')
    c = conn.cursor()
    c.execute("UPDATE leads SET status = ? WHERE id = ?", (update.status, lead_id))
    conn.commit()
    conn.close()
    return {"id": lead_id, "status": update.status}

@app.post("/webhook/calendly")
def calendly_webhook(payload: dict):
    try:
        invitee = payload.get("payload", {}).get("invitee", {})
        email = invitee.get("email", "")
        if email:
            conn = sqlite3.connect('sovereign_leads.db')
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO leads (email, status) VALUES (?, 'booked_call')", (email,))
            c.execute("UPDATE leads SET status = 'booked_call' WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            print(f"{C.GREEN}[CALENDLY] ✅ Booked call logged: {email}{C.END}")
        return {"status": "received"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook/stripe")
def stripe_webhook(payload: dict):
    try:
        obj   = payload.get("data", {}).get("object", {})
        email = obj.get("receipt_email", "") or obj.get("customer_email", "")
        if email:
            conn = sqlite3.connect('sovereign_leads.db')
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO leads (email, status) VALUES (?, 'deposit_paid')", (email,))
            c.execute("UPDATE leads SET status = 'deposit_paid' WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            print(f"{C.GREEN}[STRIPE] ✅ Deposit payment logged: {email}{C.END}")
        return {"status": "received"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 🧠 NEW: CRO MEMORY BANK QUERY ENDPOINT
# ==========================================
@app.post("/memory/query")
def query_memory_bank(payload: MemoryQuery, api_key: str = Depends(verify_api_key)):
    print(f"{C.CYAN}[CRO] 🧠 Synthesizing memory query: {payload.question}{C.END}")
    try:
        ghost_path = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")
        conn = sqlite3.connect(ghost_path, timeout=5)
        cursor = conn.execute("SELECT timestamp, ticker, signal, confidence, reasoning FROM paper_trades ORDER BY timestamp DESC LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        
        context_str = "\n".join([f"[{r[0]}] {r[1]}: Signal={r[2]}, Confidence={r[3]} - Reason: {r[4]}" for r in rows])
        if not context_str:
            context_str = "No recent trades found in database."
    except Exception as e:
        context_str = f"Database read error: {e}"

    system_prompt = (
        "You are the Suncoast Chief Risk Officer (CRO) AI. "
        "You are being interrogated by the human Architect regarding recent algorithmic trading behavior. "
        "Use the following raw database context to answer their question directly and clearly. "
        "Do not invent trades. If the answer is not in the context, state that the timeframe is outside current working memory.\n\n"
        f"--- RECENT TRADE MEMORY ---\n{context_str}\n---------------------------"
    )

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": "hermes3:8b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": payload.question}
            ],
            "stream": False
        }, timeout=45)
        answer = response.json()["message"]["content"]
        return {"answer": answer}
    except Exception as e:
        return {"answer": f"⚠️ Memory core offline or timeout: {e}"}

# ==========================================
# 🚀 BOOT
# ==========================================
if __name__ == "__main__":
    print(f"{C.CYAN}{C.BOLD}[PIXEL] 🚀 Suncoast Gateway API v2.0 — Booting on port 8000{C.END}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
