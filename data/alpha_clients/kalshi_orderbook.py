import requests
from config import cfg

class KalshiOrderbookClient:
    def get_orderbook(self, ticker: str) -> dict:
        if not cfg.KALSHI_API_KEY:
            return {"error": "Kalshi API Key missing."}
        headers = {'Authorization': f'Bearer {cfg.KALSHI_API_KEY}'}
        try:
            r = requests.get(f"{cfg.REST_BASE_URL}/markets/{ticker}/orderbook", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json().get('orderbook', {})
                return {
                    "top_bid": data.get("bids", [[0,0]])[0][0] / 100,
                    "top_ask": data.get("asks", [[0,0]])[0][0] / 100,
                    "spread": (data.get("asks", [[0,0]])[0][0] - data.get("bids", [[0,0]])[0][0]) / 100
                }
            return {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

kalshi_ob_client = KalshiOrderbookClient()
