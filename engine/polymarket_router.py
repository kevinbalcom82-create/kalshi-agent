"""
polymarket_router.py
Kalshi Agent v3.0 — Polymarket CLOB Order Execution
Signs and submits orders to Polymarket using py_clob_client.
Supports GTC (Good Till Cancelled) and FOK (Fill or Kill) order types.

REQUIRES:
    pip install py_clob_client
    .env: POLYMARKET_PRIVATE_KEY, POLYMARKET_PROXY_WALLET
"""
import os
import time
import threading
from decimal import Decimal
from typing import Optional
from config import cfg

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.constants import POLYGON
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False

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

_client      = None
_client_lock = threading.Lock()


def _get_client():
    """Singleton CLOB client — initialized once, reused for all orders."""
    global _client
    if _client is not None:
        return _client
    if not CLOB_AVAILABLE:
        return None

    with _client_lock:
        if _client is not None:
            return _client

        private_key  = os.getenv("POLYMARKET_PRIVATE_KEY")
        proxy_wallet = os.getenv("POLYMARKET_PROXY_WALLET")

        if not private_key or not proxy_wallet:
            logger.log_event("WARNING", "POLY_ROUTER", "SYSTEM",
                             "POLYMARKET_PRIVATE_KEY or POLYMARKET_PROXY_WALLET missing.")
            return None

        try:
            _client = ClobClient(
                host           = "https://clob.polymarket.com",
                chain_id       = POLYGON,
                key            = private_key,
                signature_type = 2,
                funder         = proxy_wallet
            )
            logger.log_event("INFO", "POLY_ROUTER", "SYSTEM",
                             "Polymarket CLOB client initialized.")
        except Exception as e:
            logger.log_event("ERROR", "POLY_ROUTER_INIT", "SYSTEM", str(e))
            _client = None

    return _client


def execute_polymarket_order(
    token_id:   str,
    side:       str,
    price:      Decimal,
    contracts:  int,
    order_type: str = "GTC",
    max_retries: int = 2
) -> dict:
    """
    Submits a buy or sell order to Polymarket CLOB.

    token_id:   Polymarket token ID from market_mapper
    side:       "BUY" or "SELL"
    price:      Entry price as Decimal (e.g. Decimal("0.62"))
    contracts:  Number of contracts
    order_type: "GTC" (default) or "FOK" (Fill or Kill — used for arb)

    Returns dict with success, order_id, status, error.
    """
    # Paper trading gate — always check before touching real money
    if getattr(cfg, "PAPER_TRADING", True):
        logger.log_event(
            "INFO", "POLY_PAPER_ORDER", token_id[:12],
            f"side={side} price=${price} contracts={contracts}"
        )
        return {
            "success":  True,
            "order_id": "PAPER_TRADE",
            "status":   "paper",
            "error":    None
        }

    client = _get_client()
    if not client:
        return {"success": False, "error": "CLOB client unavailable"}

    clob_order_type = (
        OrderType.FOK if order_type.upper() == "FOK"
        else OrderType.GTC
    )

    for attempt in range(max_retries + 1):
        try:
            order_args = OrderArgs(
                token_id = token_id,
                price    = float(price),
                size     = float(contracts),
                side     = side.upper(),
                type     = clob_order_type  # type: ignore
            )
            signed_order = client.create_and_post_order(order_args)

            if isinstance(signed_order, dict):
                order_id = signed_order.get("orderID", "UNKNOWN")
                status   = signed_order.get("status", "submitted")
            else:
                order_id = signed_order or "UNKNOWN"
                status   = "submitted"

            logger.log_event(
                "INFO", "POLY_ORDER_OK", token_id[:12],
                f"order_id={order_id} status={status}"
            )
            return {
                "success":  True,
                "order_id": order_id,
                "status":   status,
                "error":    None
            }

        except Exception as e:
            err = str(e).lower()
            if "nonce" in err and attempt < max_retries:
                time.sleep(1)
                continue
            if "timeout" in err and attempt < max_retries:
                time.sleep(2)
                continue
            logger.log_event("ERROR", "POLY_ORDER_FAIL", token_id[:12], str(e))
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "Max retries exceeded"}


def cancel_polymarket_order(order_id: str) -> bool:
    """
    Cancels an open Polymarket order by ID.
    Called by unified_router orphan handler when one arb leg fails.
    """
    if order_id in ("PAPER_TRADE", "UNKNOWN"):
        return True  # Nothing to cancel on paper trades

    client = _get_client()
    if not client:
        return False

    try:
        client.cancel(order_id=order_id)
        logger.log_event("INFO", "POLY_CANCEL_OK", order_id[:12], "Order cancelled.")
        return True
    except Exception as e:
        logger.log_event("ERROR", "POLY_CANCEL_FAIL", order_id[:12], str(e))
        return False
