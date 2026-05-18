"""
telegram_notifier.py
Kalshi Agent v2.0 — Telegram Alert Layer
Synchronous requests.post() — no asyncio
Silent fail on error — never crashes the agent
Single argument: send_telegram(msg: str)
"""

import requests
from config import cfg

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
REQUEST_TIMEOUT  = 10


def send_telegram(msg: str) -> bool:
    """
    Send plain-text message to configured Telegram chat.
    Returns True on success, False on any failure.
    Never raises — agent keeps running regardless.
    """
    token   = cfg.TELEGRAM_TOKEN
    chat_id = cfg.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        print("[TELEGRAM] WARNING: TOKEN or CHAT_ID not set in .env")
        return False

    url     = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id":    chat_id,
        "text":       msg,
        "parse_mode": "HTML",
    }

    try:
        resp = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return True
    except requests.exceptions.Timeout:
        print(f"[TELEGRAM] ERROR: Timed out after {REQUEST_TIMEOUT}s")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"[TELEGRAM] ERROR: HTTP {resp.status_code} — {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[TELEGRAM] ERROR: Connection failed — {e}")
        return False
    except Exception as e:
        print(f"[TELEGRAM] ERROR: Unexpected — {e}")
        return False
