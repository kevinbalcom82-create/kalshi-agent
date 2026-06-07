"""
unified_router.py
Kalshi Agent v3.0 — Cross-Exchange Arbitrage Execution Engine
Fires both legs of a Kalshi/Polymarket arbitrage simultaneously using
ThreadPoolExecutor. If one leg fills and the other fails, the orphan
handler immediately tries to close the filled leg to prevent one-sided exposure.

CRITICAL: This file moves real money on TWO exchanges at once.
PAPER_TRADING=True in your .env disables live execution in kalshi_router
but does NOT disable Polymarket orders. Set ARB_ENABLED=false to fully
disable this engine during testing.
"""
import time
import threading
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

try:
    from output.telegram_notifier import send_telegram
except ImportError:
    def send_telegram(msg): print(f"[TELEGRAM STUB] {msg}")

from engine.kalshi_router import execute_trade as kalshi_execute
from engine.polymarket_router import execute_polymarket_order, cancel_polymarket_order

# ── Fee & Spread Config ────────────────────────────────────────────────────
KALSHI_FEE_RATE     = Decimal("0.02")   # 2% taker fee
POLYMARKET_FEE_RATE = Decimal("0.02")   # 2% taker fee
MIN_GROSS_SPREAD    = Decimal("0.06")   # Minimum 6 cent spread to be worth trading
LEG_TIMEOUT_SECONDS = 10               # Max wait for both legs to confirm


def calculate_arb_spread(
    kalshi_yes_ask: Decimal,
    polymarket_yes_bid: Decimal,
    contracts: int
) -> dict:
    """
    Calculates whether an arbitrage opportunity is profitable after fees.

    Logic:
    - Buy YES on Kalshi at kalshi_yes_ask
    - Sell YES on Polymarket at polymarket_yes_bid
    - Both settle at $1.00 if YES wins — you pocket the spread minus fees

    Returns is_profitable=True only if gross spread >= MIN_GROSS_SPREAD (6 cents).
    """
    gross_spread = polymarket_yes_bid - kalshi_yes_ask
    total_fees   = (
        (kalshi_yes_ask     * KALSHI_FEE_RATE     * contracts) +
        (polymarket_yes_bid * POLYMARKET_FEE_RATE * contracts)
    )
    net_spread = gross_spread - (total_fees / contracts if contracts > 0 else Decimal("0"))

    return {
        "gross_spread":            str(round(gross_spread, 4)),
        "net_spread":              str(round(net_spread, 4)),
        "is_profitable":           gross_spread >= MIN_GROSS_SPREAD,
        "expected_profit_dollars": str(round(net_spread * contracts, 4))
    }


def _handle_orphaned_leg(
    filled_exchange: str,
    filled_order_id: str,
    failed_exchange: str,
    kalshi_ticker: str,
    polymarket_token: str,
    contracts: int,
    entry_price: Decimal
):
    """
    Emergency handler: one leg filled, the other failed.
    Tries to immediately close the filled leg to avoid one-sided exposure.
    Sends a CRITICAL Telegram alert regardless of outcome.
    """
    msg = (
        f"🚨 ORPHANED LEG DETECTED\n"
        f"Filled: {filled_exchange} | Failed: {failed_exchange}\n"
        f"Ticker: {kalshi_ticker} | Contracts: {contracts}\n"
        f"ACTION REQUIRED if auto-close fails — check both exchanges manually."
    )
    logger.log_event("CRITICAL", "ORPHANED_LEG", kalshi_ticker,
                     f"Filled on {filled_exchange}, failed on {failed_exchange}")
    send_telegram(msg)

    if filled_exchange == "KALSHI":
        # Close Kalshi leg by buying NO (opposite side)
        close_data = {
            "contracts":       contracts,
            "side":            "no",
            "entry_price":     float(entry_price),
            "capital_at_risk": str(entry_price * contracts)
        }
        try:
            kalshi_execute(close_data, kalshi_ticker)
            logger.log_event("INFO", "ORPHAN_CLOSED", kalshi_ticker,
                             "Kalshi leg closed via NO buy.")
            send_telegram(f"✅ Kalshi orphan leg closed on {kalshi_ticker}")
        except Exception as e:
            logger.log_event("CRITICAL", "ORPHAN_CLOSE_FAIL", kalshi_ticker, str(e))
            send_telegram(f"❌ Kalshi orphan close FAILED on {kalshi_ticker}: {e}")

    elif filled_exchange == "POLYMARKET":
        if cancel_polymarket_order(filled_order_id):
            logger.log_event("INFO", "ORPHAN_CLOSED", polymarket_token[:12],
                             "Polymarket leg cancelled.")
            send_telegram(f"✅ Polymarket orphan leg cancelled: {polymarket_token[:12]}")
        else:
            logger.log_event("CRITICAL", "ORPHAN_CANCEL_FAIL", polymarket_token[:12],
                             "Cancel failed — manual intervention required.")
            send_telegram(f"❌ Polymarket orphan cancel FAILED: {polymarket_token[:12]}")


def execute_arbitrage(
    kalshi_ticker: str,
    kalshi_contracts: int,
    kalshi_price: Decimal,
    polymarket_token: str,
    poly_contracts: int,
    poly_price: Decimal
) -> dict:
    """
    Fires both exchange legs simultaneously.
    Uses ThreadPoolExecutor so Kalshi and Polymarket orders go out at the same time
    rather than sequentially — critical for capturing thin arb spreads.

    Returns:
        success=True          — both legs filled
        leg_risk_triggered    — one leg filled, orphan handler fired
        error                 — both legs failed or timeout
    """
    # Hard gate — respect the global arb enable flag
    if not cfg.__dict__.get("ARB_ENABLED", True):
        logger.log_event("INFO", "ARB_DISABLED", kalshi_ticker,
                         "ARBED_ENABLED=false — skipping.")
        return {"success": False, "error": "arb_disabled"}

    result = {
        "success":             False,
        "leg_risk_triggered":  False,
        "error":               None
    }

    kalshi_data = {
        "contracts":       kalshi_contracts,
        "side":            "yes",
        "entry_price":     float(kalshi_price),
        "capital_at_risk": str(kalshi_price * kalshi_contracts)
    }

    def run_kalshi():
        try:
            kalshi_execute(kalshi_data, kalshi_ticker)
            return {"success": True, "order_id": "SUBMITTED"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_polymarket():
        return execute_polymarket_order(
            token_id=polymarket_token,
            side="BUY",
            price=poly_price,
            contracts=poly_contracts,
            order_type="FOK"   # Fill-or-Kill — never leave a partial open
        )

    # Fire both legs simultaneously
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures     = {
            executor.submit(run_kalshi):     "KALSHI",
            executor.submit(run_polymarket): "POLYMARKET"
        }
        completed   = {}
        try:
            for future in as_completed(futures, timeout=LEG_TIMEOUT_SECONDS):
                completed[futures[future]] = future.result()
        except TimeoutError:
            result["error"] = "execution_timeout"
            send_telegram(
                f"⚠️ ARB TIMEOUT on {kalshi_ticker} — "
                f"check both exchanges immediately."
            )
            return result

    kalshi_ok = completed.get("KALSHI",     {}).get("success", False)
    poly_ok   = completed.get("POLYMARKET", {}).get("success", False)

    if kalshi_ok and poly_ok:
        result["success"] = True
        logger.log_event("INFO", "ARB_SUCCESS", kalshi_ticker,
                         f"Both legs filled. Spread captured.")

    elif kalshi_ok and not poly_ok:
        result["leg_risk_triggered"] = True
        _handle_orphaned_leg(
            "KALSHI",
            completed.get("KALSHI", {}).get("order_id", ""),
            "POLYMARKET",
            kalshi_ticker, polymarket_token,
            kalshi_contracts, kalshi_price
        )

    elif poly_ok and not kalshi_ok:
        result["leg_risk_triggered"] = True
        _handle_orphaned_leg(
            "POLYMARKET",
            completed.get("POLYMARKET", {}).get("order_id", ""),
            "KALSHI",
            kalshi_ticker, polymarket_token,
            poly_contracts, poly_price
        )

    else:
        result["error"] = "both_legs_failed"
        logger.log_event("ERROR", "ARB_BOTH_FAILED", kalshi_ticker,
                         "Both legs failed — no exposure created.")

    return result
