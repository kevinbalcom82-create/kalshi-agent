import time, threading
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

def send_telegram(msg): print(f"[TELEGRAM] {msg}")

from engine.kalshi_router import execute_trade as kalshi_execute
from engine.polymarket_router import execute_polymarket_order, cancel_polymarket_order

KALSHI_FEE_RATE = Decimal("0.02")
POLYMARKET_FEE_RATE = Decimal("0.02")
MIN_GROSS_SPREAD = Decimal("0.06")
LEG_TIMEOUT_SECONDS = 10

def calculate_arb_spread(kalshi_yes_ask: Decimal, polymarket_yes_bid: Decimal, contracts: int) -> dict:
    gross_spread = polymarket_yes_bid - kalshi_yes_ask
    total_fees = (kalshi_yes_ask * KALSHI_FEE_RATE * contracts) + (polymarket_yes_bid * POLYMARKET_FEE_RATE * contracts)
    net_spread = gross_spread - (total_fees / contracts)
    is_profitable = gross_spread >= MIN_GROSS_SPREAD
    return {
        "gross_spread": str(round(gross_spread, 4)), "net_spread": str(round(net_spread, 4)),
        "is_profitable": is_profitable, "expected_profit_dollars": str(round(net_spread * contracts, 4))
    }

def _handle_orphaned_leg(filled_exchange: str, filled_order_id: str, failed_exchange: str, kalshi_ticker: str, polymarket_token: str, contracts: int, entry_price: Decimal):
    logger.log_event("CRITICAL", "ORPHANED_LEG", kalshi_ticker, f"Filled on {filled_exchange}, failed on {failed_exchange}")
    if filled_exchange == "KALSHI":
        close_data = {"contracts": contracts, "side": "no", "entry_price": float(entry_price), "capital_at_risk": str(entry_price * contracts)}
        try:
            kalshi_execute(close_data, kalshi_ticker)
            logger.log_event("INFO", "ORPHAN_CLOSED", kalshi_ticker, "Kalshi leg closed.")
        except Exception as e:
            logger.log_event("CRITICAL", "ORPHAN_CLOSE_FAIL", kalshi_ticker, str(e))
    elif filled_exchange == "POLYMARKET":
        if cancel_polymarket_order(filled_order_id):
            logger.log_event("INFO", "ORPHAN_CLOSED", polymarket_token[:12], "Polymarket leg cancelled.")

def execute_arbitrage(kalshi_ticker: str, kalshi_contracts: int, kalshi_price: Decimal, polymarket_token: str, poly_contracts: int, poly_price: Decimal) -> dict:
    result = {"success": False, "leg_risk_triggered": False, "error": None}
    kalshi_data = {"contracts": kalshi_contracts, "side": "yes", "entry_price": float(kalshi_price), "capital_at_risk": str(kalshi_price * kalshi_contracts)}
    
    def run_kalshi():
        try: kalshi_execute(kalshi_data, kalshi_ticker); return {"success": True, "order_id": "SUBMITTED"}
        except Exception as e: return {"success": False, "error": str(e)}

    def run_polymarket(): return execute_polymarket_order(token_id=polymarket_token, side="BUY", price=poly_price, contracts=poly_contracts, order_type="FOK")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(run_kalshi): "KALSHI", executor.submit(run_polymarket): "POLYMARKET"}
        completed = {}
        try:
            for future in as_completed(futures, timeout=LEG_TIMEOUT_SECONDS): completed[futures[future]] = future.result()
        except TimeoutError:
            result["error"] = "execution_timeout"
            
    kalshi_ok = completed.get("KALSHI", {}).get("success", False)
    poly_ok = completed.get("POLYMARKET", {}).get("success", False)
    
    if kalshi_ok and poly_ok: result["success"] = True
    elif kalshi_ok and not poly_ok: result["leg_risk_triggered"] = True; _handle_orphaned_leg("KALSHI", completed.get("KALSHI", {}).get("order_id"), "POLYMARKET", kalshi_ticker, polymarket_token, kalshi_contracts, kalshi_price)
    elif poly_ok and not kalshi_ok: result["leg_risk_triggered"] = True; _handle_orphaned_leg("POLYMARKET", completed.get("POLYMARKET", {}).get("order_id"), "KALSHI", kalshi_ticker, polymarket_token, poly_contracts, poly_price)
    else: result["error"] = "both_legs_failed"
    return result
