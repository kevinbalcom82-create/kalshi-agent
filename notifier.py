import requests
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

def push_alert(message: str, alert_type: str = "INFO"):
    """Pushes a real-time alert to the Telegram app."""
    
    prefix = "ℹ️"
    if alert_type == "TRADE": prefix = "🎯"
    elif alert_type == "VETO": prefix = "🛡️"
    elif alert_type == "CRITICAL": prefix = "🚨"
    
    formatted_msg = f"{prefix} **{alert_type} ALERT**\n{message}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": formatted_msg, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        pass

if __name__ == '__main__':
    push_alert("Push notification module online and synced to core engine.", "SYSTEM")
