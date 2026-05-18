import requests
from decimal import Decimal
from config import cfg
from output.agent_logger import logger

def get_market_price(ticker: str) -> Decimal:
    if not ticker: return Decimal("0.00")
    try:
        url = f"{cfg.REST_BASE_URL}/trade-api/v2/markets/{ticker}"
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        
        if response.status_code != 200: return Decimal("0.00")
            
        data = response.json()
        market_data = data.get("market", {})
        
        # 2026 Standard: Prices come as strings. Convert safely to Decimal.
        ask_val = market_data.get("yes_ask_dollars")
        if ask_val:
            return Decimal(str(ask_val))
        
        # Fallback to integer cents if dollars not present
        ask_cents = market_data.get("yes_ask", 0)
        return Decimal(str(ask_cents)) / Decimal("100")

    except Exception as e:
        logger.log_event("ERROR", "MARKET_FETCH_FAIL", ticker, str(e))
        return Decimal("0.00")
