import time, requests
from decimal import Decimal
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

CACHE_TTL = 300
_cache = {}

def resolve_kalshi_ticker(series_prefix: str) -> tuple[str, Decimal]:
    now = time.time()
    if series_prefix in _cache and now - _cache[series_prefix][0] < CACHE_TTL:
        return _cache[series_prefix][1], _cache[series_prefix][2]

    if not cfg.KALSHI_API_KEY: return series_prefix, Decimal("0.50")
    headers = {"Authorization": f"Bearer {cfg.KALSHI_API_KEY}", "Accept": "application/json"}
    try:
        resp = requests.get(f"{cfg.REST_BASE_URL}/trade-api/v2/markets", headers=headers, params={"series_ticker": series_prefix, "status": "open", "limit": 10}, timeout=5)
        if resp.status_code != 200 or not resp.json().get("markets"): return series_prefix, Decimal("0.50")
        markets = resp.json().get("markets", [])
        
        best_ticker, best_price, best_dist = None, Decimal("0.50"), Decimal("1.0")
        for market in markets:
            ticker, ask_raw = market.get("ticker"), market.get("yes_ask") or market.get("yes_ask_dollars")
            if not ticker or not ask_raw: continue
            try:
                ask = Decimal(str(ask_raw))
                if ask > Decimal("1"): ask = ask / Decimal("100")
                dist = abs(ask - Decimal("0.50"))
                if dist < best_dist: best_dist, best_ticker, best_price = dist, ticker, ask
            except Exception: continue
            
        if not best_ticker: best_ticker = markets[0].get("ticker", series_prefix)
        _cache[series_prefix] = (now, best_ticker, best_price)
        logger.log_event("INFO", "RESOLVER", series_prefix, f"Resolved: {best_ticker} @ ${best_price}")
        return best_ticker, best_price
    except Exception as e:
        logger.log_event("ERROR", "RESOLVER", series_prefix, str(e))
        return series_prefix, Decimal("0.50")

def get_resolved_price(series_prefix: str) -> Decimal: return resolve_kalshi_ticker(series_prefix)[1]
def invalidate_cache(series_prefix: str) -> None: _cache.pop(series_prefix, None)
