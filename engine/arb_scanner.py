import time, threading, requests
from decimal import Decimal
from typing import Callable
from config import cfg
from engine.kalshi_ticker_resolver import resolve_kalshi_ticker
from engine.market_mapper import resolve_polymarket_twin
from engine.unified_router import calculate_arb_spread, execute_arbitrage

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

SCAN_INTERVAL_SECONDS = 30
MIN_CONTRACTS = 5
MAX_CONTRACTS = 50

def _fetch_polymarket_bid(token_id: str) -> Decimal:
    try:
        resp = requests.get("https://clob.polymarket.com/book", params={"token_id": token_id}, timeout=5)
        if resp.status_code != 200: return Decimal("0")
        bids = resp.json().get("bids", [])
        if not bids: return Decimal("0")
        return Decimal(str(max(bids, key=lambda x: float(x.get("price", 0))).get("price", "0")))
    except Exception: return Decimal("0")

def _scan_once(strategy_tickers: list[str], reserve_fn: Callable, release_fn: Callable) -> None:
    for series_prefix in strategy_tickers:
        try:
            exact_ticker, kalshi_ask = resolve_kalshi_ticker(series_prefix)
            if kalshi_ask <= Decimal("0"): continue
            
            twin = resolve_polymarket_twin(exact_ticker)
            if not twin or not twin.get("token_ids"): continue
            poly_token = twin["token_ids"][0]
            
            poly_bid = _fetch_polymarket_bid(poly_token)
            if poly_bid <= Decimal("0"): continue
            
            spread_data = calculate_arb_spread(kalshi_ask, poly_bid, MIN_CONTRACTS)
            gross_spread, net_spread, is_profitable = Decimal(spread_data["gross_spread"]), Decimal(spread_data["net_spread"]), spread_data["is_profitable"]
            
            try:
                from output.agent_logger import logger as agent_logger
                agent_logger.log_arb_spread(exact_ticker, poly_token, kalshi_ask, poly_bid, gross_spread, net_spread, is_profitable, False)
            except Exception: pass
            
            if not is_profitable: continue
            logger.log_event("INFO", "ARB_EDGE_FOUND", exact_ticker, f"Gross: ${gross_spread} | Net: ${net_spread}")
            
            contracts = max(MIN_CONTRACTS, min(int(Decimal(str(cfg.BANKROLL)) * Decimal("0.10") / kalshi_ask), MAX_CONTRACTS))
            capital_needed = kalshi_ask * contracts
            
            if not reserve_fn(capital_needed): continue
            
            try:
                result = execute_arbitrage(exact_ticker, contracts, kalshi_ask, poly_token, contracts, poly_bid)
                if result.get("success", False):
                    try:
                        agent_logger.log_arb_spread(exact_ticker, poly_token, kalshi_ask, poly_bid, gross_spread, net_spread, True, True)
                    except Exception: pass
                if result.get("leg_risk_triggered"): release_fn(capital_needed)
            except Exception:
                release_fn(capital_needed)
        except Exception: continue

def start_arb_scanner(strategy_tickers: list[str], reserve_fn: Callable, release_fn: Callable) -> threading.Thread:
    def _loop():
        time.sleep(15)
        while True:
            try: _scan_once(strategy_tickers, reserve_fn, release_fn)
            except Exception: pass
            time.sleep(SCAN_INTERVAL_SECONDS)
    t = threading.Thread(target=_loop, daemon=True, name="ArbScanner")
    t.start()
    return t
