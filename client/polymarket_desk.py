"""
polymarket_desk.py - Web3 Execution Lane
Suncoast Agent Factory — Polymarket CLOB integration.
"""
import os
import sqlite3
import requests
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any, cast

try:
    from py_clob_client.client import ClobClient
except ImportError:
    ClobClient = None
    print("[FATAL] py-clob-client missing. Execution will fail. Run: pip install py-clob-client")

# ── Logging Setup (Matches Harvester SQLite Schema) ───────────
DB_PATH = os.path.expanduser("~/kalshi_agent/sovereign_leads.db")

def log_event(module: str, action: str, details: str):
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {module:<16} | {action:<20} | {str(details)[:120]}")
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            "INSERT INTO system_logs (module, action, details) VALUES (?, ?, ?)",
            (module, action, str(details)[:500])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOG_ERROR] {e}")

# ── API & Auth ────────────────────────────────────────────────
def get_poly_client():
    if ClobClient is None:
        raise ImportError("py-clob-client missing. Install with: pip install py-clob-client")

    host = "https://clob.polymarket.com"
    chain_id = 137 # Polygon Mainnet
    key = os.getenv("POLYGON_PRIVATE_KEY")
    funder = os.getenv("POLYGON_PUBLIC_KEY")
    
    if not key or not funder:
        raise ValueError("POLYGON_PRIVATE_KEY or POLYGON_PUBLIC_KEY missing from .env")
        
    # signature_type=1 enforces Level 1 EOA signing (no proxy requirement)
    client = ClobClient(host, key=key, chain_id=chain_id, signature_type=1, funder=funder)
    credential_factory = getattr(client, "create_or_derive_creds", None) or getattr(client, "create_creds", None)
    if credential_factory is None:
        raise AttributeError("ClobClient credential creation method not found. Update py-clob-client.")
    creds = credential_factory()
    # Prefer standard setter, but be tolerant of different client implementations
    setter = getattr(client, "set_creds", None) or getattr(client, "setCredentials", None)
    if callable(setter):
        setter(creds)
    else:
        # Fallback: attach creds directly to the client object to preserve functionality
        try:
            setattr(client, "creds", creds)
            log_event("POLYMARKET", "CRED_FALLBACK", "set_creds not found; attached creds to client.creds")
        except Exception:
            raise AttributeError("ClobClient missing method to set credentials (set_creds). Update py-clob-client.")
    return client

def resolve_market_token(slug: str, target_outcome: str = "Yes") -> Optional[str]:
    """
    Queries Polymarket's Gamma API to retrieve the exact ERC-1155 Token ID
    for a given market slug and outcome.
    """
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        if not data:
            log_event("POLYMARKET", "TOKEN_FETCH_FAIL", f"No market found for slug: {slug}")
            return None
            
        markets = data[0].get("markets", [])
        if not markets:
            return None
            
        # Target the primary active market in the event
        primary_market = markets[0]
        outcomes = json.loads(primary_market.get("outcomes", "[]"))
        token_ids = json.loads(primary_market.get("clobTokenIds", "[]"))
        
        for i, outcome in enumerate(outcomes):
            if outcome.lower() == target_outcome.lower():
                token_id = token_ids[i]
                log_event("POLYMARKET", "TOKEN_RESOLVED", f"{slug} ({outcome}) -> {token_id}")
                return token_id
                
        log_event("POLYMARKET", "TOKEN_MISMATCH", f"Outcome '{target_outcome}' not found in {outcomes}")
        return None
        
    except Exception as e:
        log_event("POLYMARKET", "API_ERROR", str(e))
        return None

# ── Execution Core ────────────────────────────────────────────
def execute_polygon_trade(signal_data: dict):
    if ClobClient is None:
        log_event("POLYMARKET", "SYSTEM_ERROR", "PyCLOB dependency missing. Aborting.")
        return False

    sig = signal_data.get("signal")
    conf = int(signal_data.get("confidence", 0))
    raw_entry = signal_data.get("suggested_entry_dollars")
    entry_price = float(raw_entry) if raw_entry is not None else 0.50
    
    # Target passed from the signal generator.
    target_slug = signal_data.get("target_slug", "will-the-fed-cut-rates-in-november-2026")
    target_outcome = "Yes" if sig in ["BULLISH", "YES"] else "No"
    
    log_event("POLYMARKET", "ORDER_INIT", f"Target: {target_slug} | {target_outcome} @ ${entry_price}")
    
    # Circuit Breakers
    if entry_price > 0.90 or entry_price < 0.10:
        log_event("POLYMARKET", "REJECTED", f"Price ${entry_price} out of bounds.")
        return False

    if conf < 75:
        log_event("POLYMARKET", "REJECTED", f"Confidence {conf}% fails 75% threshold.")
        return False
    
    try:
        client = get_poly_client()
        target_token_id = resolve_market_token(target_slug, target_outcome)
        
        if not target_token_id:
            log_event("POLYMARKET", "ROUTING_ERROR", "Token ID resolution failed. Aborting execution.")
            return False
            
        size = 10 # Hardcoded max exposure for initial live testing
        
        order_args = cast(Any, {
            "token_id": target_token_id,
            "price": entry_price,
            "size": size,
            "side": "BUY", # Always BUY the specific YES/NO token on Polymarket
            "fee_rate_bps": 0
        })
        
        log_event("POLYMARKET", "SIGNING", "Signing EIP-712 limit order...")
        response = client.create_and_post_order(order_args)
        
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                response = {"error_msg": response}
        elif not isinstance(response, dict):
            response = {}

        if response.get("success"):
            order_id = response.get("orderID", "UNKNOWN")
            log_event("POLYMARKET", "ORDER_POSTED", f"Filled {size} shares. ID: {order_id}")
            return True
        else:
            error_msg = response.get("error_msg", "Unknown CLOB error")
            log_event("POLYMARKET", "ORDER_FAILED", f"CLOB Rejected: {error_msg}")
            return False
            
    except Exception as e:
        log_event("POLYMARKET", "CRASH", str(e))
        return False
