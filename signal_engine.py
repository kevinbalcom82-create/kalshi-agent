"""
signal_engine.py
Kalshi Agent v2.3 — Local Ollama Signal Engine
Improvements over v2.2:
- temperature: 0.1 for consistent structured JSON output
- Entry price validation — clamps to 0.01-0.99 range
- Better error messages for debugging
- log_signal() added for backtesting win rate tracking
"""

import time
import json
import requests
from decimal import Decimal, InvalidOperation

from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, level, event_type, ticker, msg):
            print(f"[{level}] {event_type} | {ticker} | {msg}")
        def log_signal(self, *a, **kw): pass
    logger = _FallbackLogger()

try:
    from output.telegram_notifier import send_telegram
except ImportError:
    def send_telegram(msg): print(f"[TELEGRAM] {msg}")


# ── Configuration ─────────────────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"


# ── Entry Price Validator ─────────────────────────────────────────────────────

def _validate_entry_price(raw: str, kalshi_ask: str = "0.50") -> str:
    """
    Clamps suggested_entry_dollars to valid prediction market range 0.01-0.99.
    If model returns $10.00 or any value > 0.99, use current ask price instead.
    """
    try:
        val = Decimal(str(raw))
        if val > Decimal("0.99") or val < Decimal("0.01"):
            # Model returned a dollar amount — use ask price as fallback
            ask = Decimal(str(kalshi_ask))
            clamped = max(Decimal("0.01"), min(Decimal("0.99"), ask))
            return str(round(clamped, 2))
        return str(round(val, 2))
    except (InvalidOperation, TypeError):
        return "0.50"


# ── Main Signal Generator ─────────────────────────────────────────────────────

def generate_signal(context: dict) -> dict | None:
    """
    Calls local Ollama model with assembled context prompt.
    Returns parsed signal dict or None on failure.
    Logs every attempt — both successes and failures — for backtesting.
    """
    ticker  = context.get("ticker", "UNKNOWN")
    prompt  = context.get("prompt")
    ask_str = str(context.get("kalshi_snapshot", {}).get("yes_ask") or "0.50")

    if not prompt:
        logger.log_event("ERROR", "SIGNAL_ENGINE", ticker, "No prompt in context.")
        return None

    max_retries = 2
    text = None

    # ── API Call with retry on network error only ─────────────────────────────
    for attempt in range(max_retries + 1):
        try:
            payload = {
                "model":   OLLAMA_MODEL,
                "prompt":  prompt,
                "format":  "json",
                "stream":  False,
                "options": {
                    "temperature": 0.1,   # Low temp = consistent JSON structure
                    "top_p":       0.9,
                    "num_predict": 300,   # Enough for our JSON output
                }
            }
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            response.raise_for_status()
            text = response.json().get("response", "")
            break

        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                logger.log_event("WARNING", "OLLAMA_RETRY", ticker,
                                 f"Attempt {attempt+1} failed: {e} — retrying in 3s")
                time.sleep(3)
            else:
                logger.log_event("ERROR", "OLLAMA_FAILURE", ticker,
                                 f"All {max_retries+1} attempts failed: {e}")
                return None

    if not text:
        logger.log_event("ERROR", "OLLAMA_EMPTY", ticker, "Empty response from Ollama.")
        return None

    # ── Strip markdown fences ─────────────────────────────────────────────────
    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    # ── Parse JSON — no retry on parse failure ────────────────────────────────
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.log_event("ERROR", "SIGNAL_JSON_PARSE", ticker,
                         f"JSON parse failed: {e} | Raw: {text[:200]}")
        return None

    # ── Validate required keys ────────────────────────────────────────────────
    required = {"signal", "confidence", "suggested_entry_dollars",
                "risk_flag", "edge_source", "reasoning"}
    missing  = required - data.keys()
    if missing:
        logger.log_event("ERROR", "SIGNAL_VALIDATION", ticker,
                         f"Missing keys: {missing}")
        return None

    # ── Normalize and validate values ─────────────────────────────────────────
    try:
        confidence = max(0, min(100, int(data.get("confidence", 0))))
    except (ValueError, TypeError):
        confidence = 0

    signal_type = str(data.get("signal", "WATCH")).upper()
    if signal_type not in ("BUY_YES", "BUY_NO", "HOLD", "WATCH"):
        signal_type = "WATCH"

    # Clamp entry price to valid prediction market range
    entry_price = _validate_entry_price(
        str(data.get("suggested_entry_dollars", "0.50")),
        ask_str
    )
    data["suggested_entry_dollars"] = entry_price
    data["confidence"]              = confidence
    data["signal"]                  = signal_type

    # ── Log to signals table for backtesting ─────────────────────────────────
    try:
        logger.log_signal(
            ticker      = ticker,
            signal      = signal_type,
            confidence  = confidence,
            entry_price = entry_price,
            risk_flag   = data.get("risk_flag"),
            edge_source = data.get("edge_source"),
            reasoning   = data.get("reasoning"),
        )
    except Exception as e:
        # log_signal failure must never block the alert
        logger.log_event("WARNING", "LOG_SIGNAL_FAIL", ticker, str(e))

    logger.log_event("INFO", "SIGNAL_GENERATED", ticker, json.dumps(data))

    # ── Telegram gate ─────────────────────────────────────────────────────────
    try:
        threshold = int(getattr(cfg, "SIGNAL_CONFIDENCE_THRESHOLD", 65))
    except (ValueError, TypeError):
        threshold = 65

    if confidence >= threshold and signal_type not in ("WATCH", "HOLD"):
        msg = (
            f"⚡ KALSHI SIGNAL ALERT (LOCAL AI) ⚡\n\n"
            f"🎯 Target: {ticker}\n"
            f"📈 Signal: {signal_type}\n"
            f"🔥 Confidence: {confidence}%\n"
            f"💰 Entry Price: ${entry_price} "
            f"(= {int(float(entry_price)*100)}% implied probability)\n"
            f"⚠️  Risk: {data.get('risk_flag')}\n"
            f"🧠 Edge: {data.get('edge_source')}\n\n"
            f"📝 {data.get('reasoning')}"
        )
        send_telegram(msg)

    return data


if __name__ == "__main__":
    print(f"[*] Signal Engine — model: {OLLAMA_MODEL}")
    print("[*] Requires Ollama running and model pulled.")
