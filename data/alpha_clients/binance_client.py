import requests

class CryptoClient:
    def get_crypto_depth(self, symbol: str = "BTC-USD") -> dict:
        # Pivoted to Coinbase to avoid Binance Geo-blocks
        url = f"https://api.exchange.coinbase.com/products/{symbol}/book"
        try:
            r = requests.get(url, params={"level": "2"}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                # Coinbase returns ['price', 'size', num-orders]
                bids = [float(b[1]) for b in data.get('bids', [])[:5]]
                asks = [float(a[1]) for a in data.get('asks', [])[:5]]
                return {
                    "exchange": "Coinbase",
                    "symbol": symbol,
                    "bid_wall_vol": round(sum(bids), 2),
                    "ask_wall_vol": round(sum(asks), 2),
                    "pressure": "BULLISH" if sum(bids) > sum(asks) else "BEARISH"
                }
            return {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"error": str(e)}

# Keeping the variable name 'binance_client' so we don't break your existing imports
binance_client = CryptoClient()
