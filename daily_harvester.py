"""
daily_harvester.py
Suncoast Agent Factory — Continuous Daily Harvester v2.0
Multi-Lane Routing (Kalshi + Polymarket) with Anti-Slop Strict JSON.
"""

import os
import sys
import json
import time
import sqlite3
import requests
import traceback
from datetime import datetime

# ── Path bootstrap ─────────────────────────────────────────────────────────────
ROOT = os.path.expanduser("~/kalshi_agent")
sys.path.insert(0, ROOT)

# ── Config ─────────────────────────────────────────────────────────────────────
try:
    from config import cfg
    PAPER_TRADING = getattr(cfg, "PAPER_TRADING", True)
except ImportError:
    PAPER_TRADING = True  # Failsafe: Default to shadow mode if config is missing

DB_PATH         = os.path.join(ROOT, "sovereign_leads.db")
GHOST_DB_PATH   = os.path.join(ROOT, "output", "ghost_book.db")
OLLAMA_URL      = "http://localhost:11434/api/generate"
OLLAMA_MODEL    = "hermes3:8b"
HARVEST_SYMBOLS = ["^GSPC", "^VIX", "^NDX", "GC=F", "CL=F"]
CYCLE_INTERVAL  = 3600
MIN_CONFIDENCE  = 50

# ── WAL-mode SQLite ─────────────────────────────────────────────────────────────
def get_conn(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def ensure_tables():
    with get_conn(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                module    TEXT,
                action    TEXT,
                details   TEXT
            )
        """)
    os.makedirs(os.path.dirname(GHOST_DB_PATH), exist_ok=True)
    with get_conn(GHOST_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp             DATETIME DEFAULT CURRENT_TIMESTAMP,
                ticker                TEXT,
                signal                TEXT,
                confidence            INTEGER,
                outcome               TEXT DEFAULT 'PENDING',
                simulated_entry_price TEXT,
                reasoning             TEXT
            )
        """)

# ── Logging ─────────────────────────────────────────────────────────────────────
def log_event(module: str, action: str, details: str):
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {module:<16} | {action:<20} | {str(details)[:120]}")
        with get_conn(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO system_logs (module, action, details) VALUES (?, ?, ?)",
                (module, action, str(details)[:500])
            )
    except Exception as e:
        print(f"[LOG_ERROR] {e}")

def log_paper_trade(ticker: str, signal: dict):
    try:
        with get_conn(GHOST_DB_PATH) as conn:
            conn.execute(
                """INSERT INTO paper_trades
                   (ticker, signal, confidence, simulated_entry_price, reasoning)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    ticker,
                    signal.get("signal", "WATCH"),
                    int(signal.get("confidence", 0)),
                    str(signal.get("suggested_entry_dollars", "0.50")),
                    str(signal.get("reasoning", ""))[:500],
                )
            )
    except Exception as e:
        log_event("GHOST_BOOK", "WRITE_ERROR", str(e))

# ── Step 1: Market data ─────────────────────────────────────────────────────────
def fetch_market_data() -> dict:
    try:
        from data.yfinance_client import yfinance_client
    except ImportError as e:
        log_event("HARVESTER", "IMPORT_ERROR", f"yfinance_client unavailable: {e}")
        return {}

    results = {}
    for symbol in HARVEST_SYMBOLS:
        try:
            snapshot = yfinance_client.get_snapshot(symbol)
            if snapshot:
                results[symbol] = snapshot
                log_event("YFINANCE", "SNAPSHOT_OK",
                          f"{symbol} @ {snapshot.get('price','?')} ({snapshot.get('pct_change','0')}%)")
            else:
                log_event("YFINANCE", "SNAPSHOT_EMPTY", f"{symbol} returned no data")
        except Exception as e:
            log_event("YFINANCE", "SNAPSHOT_FAIL", f"{symbol}: {e}")

    return results

# ── Step 2: News sentiment ───────────────────────────────────────────────────────
def fetch_news_sentiment(ticker: str = "EQUITIES") -> dict:
    try:
        from data.news_client import news_client
        sentiment = news_client.get_sentiment(ticker)
        log_event("NEWS", "SENTIMENT_OK",
                  f"{ticker} score={sentiment.get('sentiment_score', 0)}")
        return sentiment
    except Exception as e:
        log_event("NEWS", "SENTIMENT_FAIL", str(e))
        return {"headlines": [], "sentiment_score": 0.0, "gdelt_tone": 0.0}

# ── Step 3: Ollama macro analysis ───────────────────────────────────────────────
def run_ollama_sentiment(market_data: dict, news: dict) -> dict:
    spx  = market_data.get("^GSPC", {})
    vix  = market_data.get("^VIX",  {})
    ndx  = market_data.get("^NDX",  {})
    gold = market_data.get("GC=F",  {})
    oil  = market_data.get("CL=F",  {})

    prompt = f"""You are a quantitative macro analyst. Analyze the live market snapshot below and return a JSON sentiment signal.

MARKET SNAPSHOT:
- S&P 500:  {spx.get('price', 'N/A')} ({spx.get('pct_change', '0')}% change)
- VIX:      {vix.get('price', 'N/A')}
- NASDAQ:   {ndx.get('price', 'N/A')} ({ndx.get('pct_change', '0')}% change)
- Gold:     {gold.get('price', 'N/A')} ({gold.get('pct_change', '0')}% change)
- Oil:      {oil.get('price', 'N/A')} ({oil.get('pct_change', '0')}% change)
- News Sentiment Score: {news.get('sentiment_score', 0.0)}

CALIBRATION RULES:
- BULLISH: VIX < 18 AND SPX change > 0.3%
- BEARISH: VIX > 22 OR SPX change < -0.5%
- NEUTRAL: everything else
- confidence must be 0-100 integer
- suggested_entry_dollars must be quoted string 0.01-0.85

TONE & STYLE CONSTRAINTS:
- Speak like a senior infrastructure engineer: brutally concise, highly technical, and direct.
- NEVER use AI slop buzzwords (e.g., "delve", "leverage", "testament", "tapestry", "demystify").
- NEVER use introductory filler (e.g., "Certainly!", "Here is the analysis...").
- Output a "target_slug" predicting a relevant Polymarket event (e.g., "will-the-fed-cut-rates", "spx-to-close-above-5500").

Respond ONLY with valid JSON:
{{
  "signal": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": integer,
  "suggested_entry_dollars": "0.XX",
  "risk_flag": "LOW" or "MEDIUM" or "HIGH",
  "target_slug": "polymarket-market-slug",
  "reasoning": "2 sentences max citing specific values"
}}"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200}
            },
            timeout=60
        )
        response.raise_for_status()
        raw    = response.json().get("response", "{}")
        result = json.loads(raw)
        log_event("OLLAMA", "SENTIMENT_OK",
                  f"Signal={result.get('signal')} conf={result.get('confidence')} slug={result.get('target_slug')}")
        return result
    except requests.exceptions.ConnectionError:
        log_event("OLLAMA", "OFFLINE", "Ollama not reachable — is it running?")
    except requests.exceptions.Timeout:
        log_event("OLLAMA", "TIMEOUT", "Inference timed out after 60s")
    except json.JSONDecodeError as e:
        log_event("OLLAMA", "JSON_PARSE_ERROR", str(e))
    except Exception as e:
        log_event("OLLAMA", "SENTIMENT_FAIL", str(e))

    return {
        "signal": "NEUTRAL",
        "confidence": 0,
        "suggested_entry_dollars": "0.50",
        "risk_flag": "HIGH",
        "target_slug": "none",
        "reasoning": "Ollama unavailable — defaulting to neutral."
    }

# ── Step 4: Signal engine ────────────────────────────────────────────────────────
def run_signal_engine(sentiment: dict, market_data: dict) -> dict:
    spx = market_data.get("^GSPC", {})
    context = {
        "ticker": "KXEQUITIES-SHADOW",
        "prompt": (
            f"Shadow mode signal. Macro sentiment: {sentiment.get('signal')} "
            f"at confidence {sentiment.get('confidence')}. "
            f"SPX @ {spx.get('price', 'N/A')} ({spx.get('pct_change', '0')}% change). "
            f"VIX @ {market_data.get('^VIX', {}).get('price', 'N/A')}. "
            f"Risk: {sentiment.get('risk_flag')}. Target Slug: {sentiment.get('target_slug')}. "
            f"Reasoning: {sentiment.get('reasoning', '')}. "
            "Output JSON with fields: signal, confidence, suggested_entry_dollars, "
            "risk_flag, target_slug, reasoning. Obey strict anti-slop rules."
        ),
        "market_data": market_data,
        "sentiment":   sentiment,
    }

    try:
        from engine.signal_engine import generate_signal
        result = generate_signal(context)
        log_event("SIGNAL_ENGINE", "GENERATED",
                  f"Signal={result.get('signal')} conf={result.get('confidence')}")
        return result
    except ImportError as e:
        log_event("SIGNAL_ENGINE", "IMPORT_ERROR",
                  f"Falling back to raw Ollama sentiment: {e}")
        return sentiment
    except Exception as e:
        log_event("SIGNAL_ENGINE", "FAIL", str(e))
        return sentiment

# ── Main harvest cycle ───────────────────────────────────────────────────────────
def run_harvest_cycle():
    cycle_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_event("HARVESTER", "CYCLE_START", f"Shadow harvest began at {cycle_id}")

    log_event("HARVESTER", "STEP_1_MARKET", "Fetching snapshots via yfinance")
    market_data = fetch_market_data()
    if not market_data:
        log_event("HARVESTER", "ABORT", "No market data returned — skipping this cycle")
        return

    log_event("HARVESTER", "STEP_2_NEWS", "Fetching news sentiment")
    news = fetch_news_sentiment("EQUITIES")

    log_event("HARVESTER", "STEP_3_OLLAMA", "Running Ollama macro analysis")
    sentiment = run_ollama_sentiment(market_data, news)

    log_event("HARVESTER", "STEP_4_SIGNAL", "Generating trade signal")
    signal = run_signal_engine(sentiment, market_data)

    conf = int(signal.get("confidence", 0))
    sig  = signal.get("signal", "NEUTRAL")

    # Layer 1: Always commit to the local Ghost Book
    if sig not in ("WATCH", "NEUTRAL") or conf >= MIN_CONFIDENCE:
        log_paper_trade("KXEQUITIES-SHADOW", signal)
        log_event("GHOST_BOOK", "TRADE_LOGGED",
                  f"Signal={sig} conf={conf} "
                  f"entry={signal.get('suggested_entry_dollars','?')} "
                  f"risk={signal.get('risk_flag','?')}")
                  
        # Layer 2: Split-Lane Dispatch Router
        if not PAPER_TRADING:
            log_event("EXECUTION_ROUTER", "LIVE_DISPATCH", "Routing signal to live downstream paths.")
            
            # Lane A: Low/Medium Risk Macro routes to Kalshi
            if signal.get("risk_flag") in ("LOW", "MEDIUM"):
                try:
                    from client.kalshi_desk import execute_kalshi_trade
                    execute_kalshi_trade(signal)
                except ImportError:
                    log_event("EXECUTION_ROUTER", "MISSING", "Kalshi desk module not found.")
                    
            # Lane B: High Volatility or Bearish routes to Polymarket
            vix_price = float(market_data.get("^VIX", {}).get("price", 0) or 0)
            if vix_price > 25 or sig == "BEARISH":
                try:
                    from client.polymarket_desk import execute_polygon_trade
                    execute_polygon_trade(signal)
                except ImportError:
                    log_event("EXECUTION_ROUTER", "MISSING", "Polymarket desk module not found.")
    else:
        log_event("GHOST_BOOK", "SKIP",
                  f"Signal={sig} conf={conf} — below threshold ({MIN_CONFIDENCE}), not logged")

    log_event("HARVESTER", "CYCLE_END",
              f"Complete. Next run in {CYCLE_INTERVAL // 60} min.")

# ── Scheduler ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Suncoast Agent Factory — Daily Harvester v2.0")
    mode = "Paper Mode" if PAPER_TRADING else "LIVE EXECUTION ARMED"
    print(f"  {mode} | Bare-Metal | Multi-Lane Dispatch")
    print("=" * 55)

    log_event("HARVESTER", "BOOT",
              f"Harvester online. Cycle every {CYCLE_INTERVAL // 60} min.")
    ensure_tables()

    while True:
        try:
            run_harvest_cycle()
        except KeyboardInterrupt:
            log_event("HARVESTER", "SHUTDOWN", "KeyboardInterrupt — clean exit.")
            print("\n[HARVESTER] Stopped by user.")
            break
        except Exception as e:
            log_event("HARVESTER", "UNHANDLED_ERROR", traceback.format_exc()[:400])
            print(f"[HARVESTER] Unhandled error: {e} — sleeping and retrying.")

        print(f"\n[HARVESTER] Sleeping {CYCLE_INTERVAL // 60} minutes...\n")
        try:
            time.sleep(CYCLE_INTERVAL)
        except KeyboardInterrupt:
            log_event("HARVESTER", "SHUTDOWN", "Interrupted during sleep — clean exit.")
            print("\n[HARVESTER] Stopped by user.")
            break

if __name__ == "__main__":
    main()
