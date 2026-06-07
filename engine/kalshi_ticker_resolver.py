"""
kalshi_ticker_resolver.py
Kalshi Agent v3.0 — Smart Ticker Finder
Given a series prefix (e.g. KXCPI), hits the Kalshi REST API,
retrieves all open markets in that series, and picks the contract
whose YES price is closest to $0.50 — the maximum liquidity zone.

Results cached for 5 minutes to avoid hammering the API.
Used by arb_scanner.py on every 30-second scan cycle.
"""
import time
import requests
from decimal import Decimal
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

CACHE_TTL = 300   # 5 minutes
_cache    = {}


def resolve_kalshi_ticker(series_prefix: str) -> tuple[str, Decimal]:
    """
    Resolves a series prefix to the most liquid open contract.

    Returns: (exact_ticker, yes_ask_price)
    Falls back to (series_prefix, Decimal("0.50")) on any failure.

    Logic: picks the contract whose YES ask price is closest to $0.50
    because that's where bid/ask spreads are tightest and arb is most
    likely to exist.
    """
    now = time.time()

    # Return cached result if still fresh
    if (series_prefix in _cache and
            now - _cache[series_prefix][0] < CACHE_TTL):
        return _cache[series_prefix][1], _cache[series_prefix][2]

    if not cfg.KALSHI_API_KEY:
        logger.log_event("WARNING", "RESOLVER", series_prefix,
                         "No KALSHI_API_KEY — returning default.")
        return series_prefix, Decimal("0.50")

    headers = {
        "Authorization": f"Bearer {cfg.KALSHI_API_KEY}",
        "Accept":        "application/json"
    }

    try:
        resp = requests.get(
            f"{cfg.REST_BASE_URL}/trade-api/v2/markets",
            headers = headers,
            params  = {
                "series_ticker": series_prefix,
                "status":        "open",
                "limit":         10
            },
            timeout = 5
        )

        if resp.status_code != 200 or not resp.json().get("markets"):
            return series_prefix, Decimal("0.50")

        markets = resp.json().get("markets", [])

        best_ticker = None
        best_price  = Decimal("0.50")
        best_dist   = Decimal("1.0")

        for market in markets:
            ticker  = market.get("ticker")
            ask_raw = market.get("yes_ask") or market.get("yes_ask_dollars")

            if not ticker or not ask_raw:
                continue

            try:
                ask = Decimal(str(ask_raw))
                # Normalize cents to dollars if needed
                if ask > Decimal("1"):
                    ask = ask / Decimal("100")

                dist = abs(ask - Decimal("0.50"))
                if dist < best_dist:
                    best_dist   = dist
                    best_ticker = ticker
                    best_price  = ask
            except Exception:
                continue

        if not best_ticker:
            best_ticker = markets[0].get("ticker", series_prefix)

        # Cache the result
        _cache[series_prefix] = (now, best_ticker, best_price)

        logger.log_event("INFO", "RESOLVER", series_prefix,
                         f"Resolved: {best_ticker} @ ${best_price}")
        return best_ticker, best_price

    except Exception as e:
        logger.log_event("ERROR", "RESOLVER", series_prefix, str(e))
        return series_prefix, Decimal("0.50")


def get_resolved_price(series_prefix: str) -> Decimal:
    """Convenience wrapper — returns just the price."""
    return resolve_kalshi_ticker(series_prefix)[1]


def invalidate_cache(series_prefix: str) -> None:
    """Force-expires the cache for a series — call after a known price move."""
    _cache.pop(series_prefix, None)
