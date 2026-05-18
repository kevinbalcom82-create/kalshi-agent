"""
polymarket_stream.py
Kalshi Agent v2.1 — Polymarket CLOB Stream (Drop-in replacement)
No API key or funded account required — fully public feed.

Replaces kalshi_stream.py while core_engine.py Kalshi account is unfunded.
Interface is identical — core_engine.py requires zero changes.

Polymarket CLOB API:
  REST:      https://clob.polymarket.com
  WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/market

Auth: None required for read-only market data.
"""

import json
import time
import threading
import requests
import websocket
from decimal import Decimal, InvalidOperation
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, level, event_type, ticker, msg):
            print(f"[{level}] {event_type} | {ticker} | {msg}")
    logger = _FallbackLogger()

try:
    from state.market_state import state_manager
except ImportError:
    state_manager = None


# ── Constants ─────────────────────────────────────────────────────────────────

REST_BASE   = "https://clob.polymarket.com"
WSS_URL     = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
SEARCH_TERMS = {
    "CPI":  ["CPI", "inflation", "consumer price"],
    "FED":  ["federal reserve", "fed rate", "interest rate"],
    "JOBS": ["unemployment", "nonfarm", "payroll"],
    "GDP":  ["GDP", "economic growth"],
    "PCE":  ["PCE", "personal consumption"],
}
REQUEST_TIMEOUT    = 10
RECONNECT_DELAY    = 5
MAX_RECONNECT_DELAY = 120


class PolymarketStream:
    """
    Drop-in replacement for KalshiStream.
    core_engine.py calls: stream = PolymarketStream(); stream.connect()
    """

    def __init__(self):
        self.active_ticker   = cfg.TARGET_TICKER or "CPI"
        self.condition_id    = None   # Polymarket market condition ID
        self.token_ids       = []     # YES/NO token IDs for subscription
        self.ws              = None
        self._running        = True
        self._reconnect_wait = RECONNECT_DELAY

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_active_market(self) -> bool:
        """
        Search Polymarket REST API for active market matching our ticker prefix.
        Sets self.condition_id and self.token_ids on success.
        Returns True if found, False if not.
        """
        prefix = self.active_ticker
        terms  = SEARCH_TERMS.get(prefix, [prefix])

        print(f"🔍 Searching Polymarket for live {prefix} contracts...")
        logger.log_event("INFO", "DISCOVERY", prefix, f"Searching Polymarket for: {terms}")

        for term in terms:
            try:
                resp = requests.get(
                    f"{REST_BASE}/markets",
                    params={"search": term, "active": "true", "closed": "false"},
                    timeout=REQUEST_TIMEOUT
                )
                resp.raise_for_status()
                data = resp.json()

                markets = data if isinstance(data, list) else data.get("data", [])

                for market in markets:
                    question = market.get("question", "").lower()
                    # Filter for relevant active markets
                    if any(t.lower() in question for t in terms):
                        self.condition_id = market.get("condition_id")
                        tokens = market.get("tokens", [])
                        self.token_ids = [t.get("token_id") for t in tokens if t.get("token_id")]

                        found_name = market.get("question", "Unknown")[:60]
                        print(f"✅ Found: {found_name}")
                        print(f"   Condition ID: {self.condition_id}")
                        print(f"   Token IDs: {len(self.token_ids)} found")
                        logger.log_event("INFO", "DISCOVERY_OK", prefix,
                                         f"Market: {found_name} | Condition: {self.condition_id}")

                        # Update global ticker to reflect actual market found
                        cfg.TARGET_TICKER = prefix
                        return True

            except requests.exceptions.RequestException as e:
                logger.log_event("WARNING", "DISCOVERY_NET_ERR", prefix, str(e))
                continue
            except (ValueError, KeyError) as e:
                logger.log_event("WARNING", "DISCOVERY_PARSE_ERR", prefix, str(e))
                continue

        print(f"⚠️  No active Polymarket {prefix} market found — will retry.")
        logger.log_event("WARNING", "DISCOVERY_MISS", prefix, "No matching market found.")
        return False

    # ── WebSocket ─────────────────────────────────────────────────────────────

    def connect(self):
        """
        Main entry point called by core_engine.py.
        Discovers market then runs WebSocket loop with reconnect.
        """
        discovered = self.discover_active_market()
        if not discovered:
            print("⚠️  Proceeding without confirmed market — will use ticker prefix.")

        print(f"📡 Connecting to Polymarket WebSocket...")
        logger.log_event("INFO", "WSS_CONNECT", self.active_ticker, "Initiating WebSocket connection.")

        while self._running:
            try:
                self.ws = websocket.WebSocketApp(
                    WSS_URL,
                    on_open    = self._on_open,
                    on_message = self._on_message,
                    on_error   = self._on_error,
                    on_close   = self._on_close,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)

            except Exception as e:
                logger.log_event("ERROR", "WSS_EXCEPTION", self.active_ticker, str(e))

            if not self._running:
                break

            print(f"🔄 Reconnecting in {self._reconnect_wait}s...")
            time.sleep(self._reconnect_wait)
            self._reconnect_wait = min(self._reconnect_wait * 2, MAX_RECONNECT_DELAY)

    def _on_open(self, ws):
        """Subscribe to book channel for our token IDs on connection."""
        self._reconnect_wait = RECONNECT_DELAY  # Reset backoff on success

        if self.token_ids:
            # Subscribe to order book for each token
            for token_id in self.token_ids:
                sub_msg = {
                    "type":      "subscribe",
                    "channel":   "book",
                    "assets_ids": [token_id]
                }
                ws.send(json.dumps(sub_msg))

            print(f"✅ Subscribed to {self.active_ticker} ({len(self.token_ids)} tokens)")
            logger.log_event("INFO", "WSS_SUBSCRIBED", self.active_ticker,
                             f"Subscribed to {len(self.token_ids)} token(s)")
        else:
            # No token IDs — subscribe by condition ID if available
            if self.condition_id:
                sub_msg = {
                    "type":    "subscribe",
                    "channel": "market",
                    "id":      self.condition_id
                }
                ws.send(json.dumps(sub_msg))
                print(f"✅ Subscribed via condition ID: {self.condition_id}")
            else:
                print(f"⚠️  No token IDs or condition ID — listening without subscription.")

        print("✅ System Online. Monitoring markets.")

    def _on_message(self, ws, message):
        """Route incoming Polymarket messages to state_manager."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")

        # Polymarket sends: book snapshot, price_change, last_trade_price
        if msg_type == "book":
            self._handle_book_snapshot(data)
        elif msg_type == "price_change":
            self._handle_price_change(data)
        elif msg_type == "last_trade_price":
            self._handle_last_trade(data)
        elif msg_type == "tick_size_change":
            pass  # Informational only
        elif msg_type in ("subscribed", "subscription_error"):
            logger.log_event("INFO", f"WSS_{msg_type.upper()}", self.active_ticker, str(data))

    def _handle_book_snapshot(self, data: dict):
        """
        Polymarket book snapshot:
        {type: "book", asset_id: "...", bids: [{price, size}], asks: [{price, size}]}
        Routes to state_manager.apply_snapshot() via normalized format.
        """
        if not state_manager:
            return

        ticker = self.active_ticker
        state  = state_manager.get_or_create(ticker)

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        # Polymarket YES token bids = yes_book, asks = no_book proxy
        # Convert [{price, size}] to [(price_str, count_decimal)] format
        yes_levels = [(b.get("price", "0"), b.get("size", "0")) for b in bids]
        no_levels  = [(a.get("price", "0"), a.get("size", "0")) for a in asks]

        state.apply_snapshot({"yes_dollars_fp": yes_levels, "no_dollars_fp": no_levels})

        # Also apply ticker for bid/ask top of book
        if bids and asks:
            best_bid = max(bids, key=lambda x: float(x.get("price", 0)))
            best_ask = min(asks, key=lambda x: float(x.get("price", 1)))
            state.apply_ticker({
                "yes_bid_dollars": best_bid.get("price", "0"),
                "yes_ask_dollars": best_ask.get("price", "0"),
                "ts_ms": int(time.time() * 1000),
            })

        logger.log_event("INFO", "BOOK_SNAPSHOT", ticker,
                         f"Bids: {len(bids)} | Asks: {len(asks)}")

    def _handle_price_change(self, data: dict):
        """
        Polymarket price_change:
        {type: "price_change", asset_id: "...", price: "0.54", side: "BUY"}
        Routes to state_manager.apply_ticker()
        """
        if not state_manager:
            return

        ticker = self.active_ticker
        state  = state_manager.get_or_create(ticker)
        price  = data.get("price", "0")
        side   = data.get("side", "").upper()

        if side == "BUY":
            state.apply_ticker({
                "yes_bid_dollars": price,
                "ts_ms": int(time.time() * 1000),
            })
        elif side == "SELL":
            state.apply_ticker({
                "yes_ask_dollars": price,
                "ts_ms": int(time.time() * 1000),
            })

    def _handle_last_trade(self, data: dict):
        """
        Polymarket last_trade_price:
        {type: "last_trade_price", asset_id: "...", price: "0.52"}
        Routes to state_manager.apply_ticker() as last_price
        """
        if not state_manager:
            return

        ticker = self.active_ticker
        state  = state_manager.get_or_create(ticker)
        state.apply_ticker({
            "price_dollars": data.get("price", "0"),
            "ts_ms": int(time.time() * 1000),
        })

    def _on_error(self, ws, error):
        print(f"❌ WS Error: {error}")
        logger.log_event("ERROR", "WSS_ERROR", self.active_ticker, str(error))

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"🔌 Connection closed ({close_status_code})")
        logger.log_event("WARNING", "WSS_CLOSED", self.active_ticker,
                         f"Code: {close_status_code} | Msg: {close_msg}")

    def stop(self):
        """Called by shutdown handler."""
        self._running = False
        if self.ws:
            self.ws.close()
