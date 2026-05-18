"""
kalshi_router.py
Kalshi Agent v2.4 — Live Execution Engine
Handles RSA PKCS1v15 signing and Limit Order routing to Kalshi REST API.
"""

import time
import json
import requests
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from config import cfg
from output.agent_logger import logger

class KalshiAuth:
    """Singleton to keep the RSA key in RAM, preventing disk I/O on every trade."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KalshiAuth, cls).__new__(cls)
            cls._instance._load_key()
        return cls._instance

    def _load_key(self):
        try:
            with open(cfg.KALSHI_PRIVATE_KEY_PATH, "rb") as key_file:
                self.private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                )
            self.is_loaded = True
            print("✅ Kalshi RSA Key loaded into Secure Enclave.")
        except Exception as e:
            self.is_loaded = False
            logger.log_event("ERROR", "RSA_LOAD_FAIL", "SYSTEM", str(e))

    def sign_request(self, timestamp_str: str, method: str, path: str) -> str:
        """Generates the PKCS1v15 signature required by Kalshi API v2."""
        if not self.is_loaded:
            raise ValueError("RSA key not loaded.")
            
        msg_string = timestamp_str + method + path
        signature = self.private_key.sign(
            msg_string.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')

# Initialize the Singleton
auth_manager = KalshiAuth()

def execute_trade(kelly_data: dict, ticker: str):
    """
    Takes the sizing math and routes the physical order to the exchange.
    """
    if not auth_manager.is_loaded:
        logger.log_event("ERROR", "EXEC_FAIL", ticker, "Cannot execute: RSA key missing.")
        return

    # 1. Extract Order Parameters
    contracts = kelly_data.get("contracts", 0)
    side = kelly_data.get("side", "yes").lower()
    entry_price_dollars = float(kelly_data.get("entry_price", 0))
    entry_price_cents = int(entry_price_dollars * 100)

    if contracts < 1:
        logger.log_event("INFO", "EXEC_SKIPPED", ticker, "0 contracts allocated.")
        return

    # 2. Build the Kalshi API Payload
    path = "/trade-api/v2/portfolio/orders"
    method = "POST"
    current_ts = str(int(time.time() * 1000))
    
    # Generate the Base64 RSA Signature
    try:
        signature = auth_manager.sign_request(current_ts, method, path)
    except Exception as e:
        logger.log_event("ERROR", "SIGNING_FAIL", ticker, str(e))
        return

    headers = {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": cfg.KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": current_ts
    }

    payload = {
        "ticker": ticker,
        "action": "buy",
        "type": "limit",
        "yes_price": entry_price_cents if side == "yes" else 100 - entry_price_cents,
        "no_price": entry_price_cents if side == "no" else 100 - entry_price_cents,
        "count": contracts,
        "client_order_id": f"agent_{current_ts}"
    }

    # 3. The Paper Trading Safety Net
    if getattr(cfg, "PAPER_TRADING", True):
        print("\n--- 🛡️ DRY RUN ORDER (PAPER_TRADING=True) ---")
        print(f"URL: {cfg.REST_BASE_URL}{path}")
        print(f"HEADERS: {json.dumps({k: v for k, v in headers.items() if k != 'KALSHI-ACCESS-SIGNATURE'}, indent=2)}")
        print(f"PAYLOAD: {json.dumps(payload, indent=2)}")
        print("--------------------------------------------\n")
        logger.log_event("INFO", "PAPER_ORDER", ticker, f"Would buy {contracts} {side.upper()} at {entry_price_cents}c")
        return

    # 4. Live Execution
    try:
        url = f"{cfg.REST_BASE_URL}{path}"
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        
        if response.status_code == 201 or response.status_code == 200:
            logger.log_event("INFO", "LIVE_ORDER_SUCCESS", ticker, f"Bought {contracts} {side.upper()} at {entry_price_cents}c")
        else:
            # This is where the empty account 400 error will get caught cleanly!
            logger.log_event("ERROR", "LIVE_ORDER_REJECTED", ticker, f"Code: {response.status_code} | Msg: {response.text}")
            
    except Exception as e:
        logger.log_event("ERROR", "HTTP_ROUTING_FAIL", ticker, str(e))

if __name__ == "__main__":
    # Internal Test
    print("[*] Testing Kalshi Router (Dry Run)...")
    test_data = {"contracts": 10, "side": "yes", "entry_price": 0.45}
    execute_trade(test_data, "KXCPI-26MAY-T3.8")
