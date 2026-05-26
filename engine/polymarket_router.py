import os, time, threading
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

def send_telegram(msg): print(f"[TELEGRAM] {msg}")

_client = None
_client_lock = threading.Lock()

def _get_client():
    global _client
    if _client is not None: return _client
    if not CLOB_AVAILABLE: return None
    with _client_lock:
        if _client is not None: return _client
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        proxy_wallet = os.getenv("POLYMARKET_PROXY_WALLET")
        if not private_key or not proxy_wallet: return None
        try:
            _client = ClobClient(host="https://clob.polymarket.com", chain_id=POLYGON, key=private_key, signature_type=2, funder=proxy_wallet)
            logger.log_event("INFO", "POLY_ROUTER", "SYSTEM", f"Polymarket CLOB initialized.")
        except Exception as e:
            logger.log_event("ERROR", "POLY_ROUTER_INIT", "SYSTEM", str(e))
            _client = None
    return _client

def execute_polymarket_order(token_id: str, side: str, price: Decimal, contracts: int, order_type: str = "GTC", max_retries: int = 2) -> dict:
    if getattr(cfg, "PAPER_TRADING", True):
        logger.log_event("INFO", "POLY_PAPER_ORDER", token_id[:12], f"side={side} price=${price} contracts={contracts}")
        return {"success": True, "order_id": "PAPER_TRADE", "status": "paper", "error": None}
    
    client = _get_client()
    if not client: return {"success": False, "error": "Client unavailable"}
    
    clob_order_type = OrderType.FOK if order_type.upper() == "FOK" else OrderType.GTC
    
    for attempt in range(max_retries + 1):
        try:
            order_args = OrderArgs(token_id=token_id, price=float(price), size=float(contracts), side=side.upper(), order_type=clob_order_type)
            signed_order = client.create_and_post_order(order_args)
            return {"success": True, "order_id": signed_order.get("orderID", "UNKNOWN"), "status": signed_order.get("status", "submitted"), "error": None}
        except Exception as e:
            if "nonce" in str(e).lower() and attempt < max_retries: time.sleep(1); continue
            if "timeout" in str(e).lower() and attempt < max_retries: time.sleep(2); continue
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Max retries exceeded"}

def cancel_polymarket_order(order_id: str) -> bool:
    if order_id in ("PAPER_TRADE", "UNKNOWN"): return True
    client = _get_client()
    if not client: return False
    try:
        client.cancel(order_id=order_id)
        return True
    except Exception: return False
