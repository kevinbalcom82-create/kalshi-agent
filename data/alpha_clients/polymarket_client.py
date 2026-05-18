import requests
import json

class PolymarketClient:
    def get_event_consensus(self, slug: str) -> dict:
        url = "https://gamma-api.polymarket.com/events"
        try:
            # Polymarket requires a precise slug, not a generic text query
            r = requests.get(url, params={"slug": slug, "active": "true"}, timeout=5)
            if r.status_code == 200 and r.json():
                event = r.json()[0]
                markets = event.get('markets', [])
                if markets:
                    prices_raw = markets[0].get("outcomePrices", '["0"]')
                    if isinstance(prices_raw, str):
                        try:
                            prices = json.loads(prices_raw)
                        except json.JSONDecodeError:
                            prices = ["0"]
                    else:
                        prices = prices_raw
                    
                    return {
                        "event": event.get("title"),
                        "poly_yes_price": prices[0] if prices else "0",
                        "volume": markets[0].get("volume", "0")
                    }
            return {"error": f"Market slug '{slug}' not found on Polymarket"}
        except Exception as e:
            return {"error": str(e)}

polymarket_client = PolymarketClient()
