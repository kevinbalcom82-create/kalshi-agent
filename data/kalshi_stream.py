import json
import time
import base64
import websocket
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from kalshi_python_sync import ApiClient, Configuration
from kalshi_python_sync.api import market_api
from config import cfg

class KalshiStream:
    def __init__(self):
        self.config = Configuration()
        self.config.key_id = cfg.KALSHI_API_KEY
        self.config.private_key_path = cfg.KALSHI_PRIVATE_KEY_PATH
        self.api_client = ApiClient(self.config)
        self.market_api = market_api.MarketApi(self.api_client)
        # Ensure it's never None
        self.active_ticker = cfg.TARGET_TICKER if cfg.TARGET_TICKER else "CPI"

    def discover_active_ticker(self):
        """Uses the SDK to find a real, tradable ticker name."""
        try:
            print(f"🔍 Searching for live {self.active_ticker} contracts...")
            # We look for open markets in that series
            resp = self.market_api.get_markets(limit=5, series_ticker=self.active_ticker, status="open")
            if resp.markets and len(resp.markets) > 0:
                self.active_ticker = resp.markets[0].ticker
                print(f"✅ Found: {self.active_ticker}")
            else:
                print(f"⚠️ No active {self.active_ticker} markets. Using series name.")
        except Exception as e:
            print(f"⚠️ Discovery failed: {e}")

    def connect(self):
        # 1. Discover the real ticker first
        self.discover_active_ticker()

        # 2. Handshake Setup
        timestamp = str(int(time.time() * 1000))
        path = "/trade-api/ws/v2"
        method = "GET"
        msg = f"{timestamp}{method}{path}"

        # 3. RSA Signature
        with open(cfg.KALSHI_PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        signature = private_key.sign(
            msg.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256()
        )
        encoded_sig = base64.b64encode(signature).decode()

        headers = [
            f"KALSHI-ACCESS-KEY: {cfg.KALSHI_API_KEY}",
            f"KALSHI-ACCESS-SIGNATURE: {encoded_sig}",
            f"KALSHI-ACCESS-TIMESTAMP: {timestamp}"
        ]

        print(f"📡 Connecting to {self.active_ticker} on external-api-ws...")
        self.ws = websocket.WebSocketApp(
            cfg.WSS_URL,
            header=headers,
            on_message=self.on_message,
            on_open=self.on_open,
            on_error=lambda ws, e: print(f"❌ WS Error: {e}"),
            on_close=lambda ws, c, m: print("🔌 Connection Closed")
        )
        self.ws.run_forever()

    def on_open(self, ws):
        # Only subscribe if we have a valid ticker
        if self.active_ticker:
            sub_msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_tickers": [self.active_ticker]
                }
            }
            ws.send(json.dumps(sub_msg))
            print(f"✅ Subscribed to {self.active_ticker}")

    def on_message(self, ws, message):
        data = json.loads(message)
        if any(x in str(data).lower() for x in ["orderbook_snapshot", "orderbook_delta"]):
            from state.market_state import state_manager
            state_manager.update_orderbook(self.active_ticker, data)
