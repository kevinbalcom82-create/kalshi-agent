from decimal import Decimal
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BANKROLL = Decimal(str(os.getenv("BANKROLL", "25.00")))
    HEARTBEAT_INTERVAL_SECONDS = 3600 

    REST_BASE_URL = "https://external-api.kalshi.com"
    TARGET_TICKER = os.getenv("TARGET_TICKER", "CPI")
    PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

    KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
    KALSHI_PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    FRED_API_KEY = os.getenv("FRED_API_KEY")
    BLS_API_KEY = os.getenv("BLS_API_KEY")
    DB_PATH = "/Volumes/AI_Drive/kalshi_data/market_state.db"
    
    # 🚨 Telegram Credentials (Aliased for backward compatibility!)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") 
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    def to_decimal(self, val):
        return Decimal(str(val))

cfg = Config()
