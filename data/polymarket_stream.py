"""
polymarket_stream.py
Kalshi Agent v2.3 — Polymarket CLOB Stream (Dynamic Close Time Extraction)
Includes CLOB Liquidity Verification, Synthetic Snapshot Fallback,
and dynamic extraction of the market lock-out timestamp.
"""

import json
import time
import threading
import requests
import websocket
import datetime
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
    def __init__(self):
        self.active_ticker   = cfg.TARGET_TICKER or "CPI"
        self.condition_id    = None
        self.token_ids       = []
        self.ws              = None
        self._running        = True
        self._reconnect_wait = RECONNECT_DELAY

    def discover_active_market(self) -> bool:
        prefix = self.active_ticker
        terms  = SEARCH_TERMS.get(prefix, [prefix])
        print(f"🔍 Searching Polymarket for live {prefix} contracts...")
        logger.log_event("INFO", "DISCOVERY", prefix, f"Searching for: {terms}")

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
                    if any(t.lower() in question for t in terms):
                        candidate_tokens = [t.get("token_id") for t in market.get("tokens", []) if t.get("token_id")]
                        if not candidate_tokens: 
                            continue
                            
                        self.condition_id = market.get("condition_id")
                        self.token_ids = candidate_tokens
                        found_name = market.get("question", "Unknown")[:60]
                        end_date_iso = market.get("end_date_iso", "")
                        
                        # Dynamically inject the close time into the global config
                        cfg.TARGET_CLOSE_ISO = end_date_iso
                        if end_date_iso:
                            try:
                                # Convert UTC ISO string to local UNIX timestamp
                                dt = datetime.datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
                                cfg.TARGET_CLOSE_TS = dt.timestamp()
                            except Exception as e:
                                logger.log_event("WARNING", "DISCOVERY_TIME_ERR", prefix, str(e))
                        
                        print(f"✅ Found: {found_name}")
                        if end_date_iso:
                            print(f"⏱️ Exchange Lockout Time: {end_date_iso}")
                        
                        # Verify CLOB liquidity
                        test_resp = requests.get(f"{REST_BASE}/book", params={"token_id": candidate_tokens[0]}, timeout=5)
                        if test_resp.status_code == 200:
                            print(f"✅ Verified CLOB Liquidity. Applying REST snapshot...")
                            self._handle_book_snapshot(test_resp.json())
                        else:
                            print(f"⚠️ No CLOB book yet (HTTP {test_resp.status_code}) — waiting for WebSocket data.")
                            logger.log_event("INFO", "CLOB_WAIT", prefix, "No book data yet — WebSocket will deliver.")
                            
                        cfg.TARGET_TICKER = prefix
                        return True
            except requests.exceptions.RequestException as e:
                logger.log_event("WARNING", "DISCOVERY_NET_ERR", prefix, str(e))
                continue
            except (ValueError, KeyError) as e:
                logger.log_event("WARNING", "DISCOVERY_PARSE_ERR", prefix, str(e))
                continue

        print(f"⚠️  No active Polymarket {prefix} market found.")
        return False

    def connect(self):
        discovered = self.discover_active_market()
        if not discovered:
            print("⚠️  Proceeding without confirmed market — will use ticker prefix.")
            print("⏳ Signal loop will wait for real WebSocket book data.")

        print(f"📡 Connecting to Polymarket WebSocket...")
        logger.log_event("INFO", "WSS_CONNECT", self.active_ticker, "Initiating WebSocket.")

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
            
            except (KeyboardInterrupt, SystemExit):
                print("\n🛑 Stream caught exit signal. Halting reconnect loop.")
                self._running = False
                break
            except Exception as e:
                logger.log_event("ERROR", "WSS_EXCEPTION", self.active_ticker, str(e))

            if not self._running:
                break

            print(f"🔄 Reconnecting in {self._reconnect_wait}s...")
            for _ in range(self._reconnect_wait):
                if not self._running:
                    break
                time.sleep(1)
            
            self._reconnect_wait = min(self._reconnect_wait * 2, MAX_RECONNECT_DELAY)

    def _on_open(self, ws):
        self._reconnect_wait = RECONNECT_DELAY
        if self.token_ids:
            sub_msg = {
                "type": "market",
                "assets_ids": self.token_ids
            }
            ws.send(json.dumps(sub_msg))
            print(f"✅ Subscribed to {self.active_ticker} ({len(self.token_ids)} tokens)")
            logger.log_event("INFO", "WSS_SUBSCRIBED", self.active_ticker, f"Subscribed {len(self.token_ids)} token(s)")
        else:
            print(f"⚠️  No token IDs to subscribe to.")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict): self._route_message(item)
        elif isinstance(data, dict):
            self._route_message(data)

    def _route_message(self, data: dict):
        msg_type = data.get("event_type", data.get("event", data.get("type", "")))
        
        if msg_type == "book": 
            self._handle_book_snapshot(data)
        elif msg_type == "price_change": 
            self._handle_price_change(data)
        elif msg_type == "last_trade_price": 
            self._handle_last_trade(data)
        elif msg_type in ("subscribed", "subscription_error"):
            logger.log_event("INFO", f"WSS_{msg_type.upper()}", self.active_ticker, str(data))

    def _handle_book_snapshot(self, data: dict):
        if not state_manager: return
        state = state_manager.get_or_create(self.active_ticker)
        bids, asks = data.get("bids", []), data.get("asks", [])
        
        yes_levels = [(b.get("price", "0"), b.get("size", "0")) for b in bids]
        no_levels  = [(a.get("price", "0"), a.get("size", "0")) for a in asks]
        state.apply_snapshot({"yes_dollars_fp": yes_levels, "no_dollars_fp": no_levels})

        if bids and asks:
            best_bid = max(bids, key=lambda x: float(x.get("price", 0)))
            best_ask = min(asks, key=lambda x: float(x.get("price", 1)))
            state.apply_ticker({
                "yes_bid_dollars": best_bid.get("price", "0"),
                "yes_ask_dollars": best_ask.get("price", "0"),
                "ts_ms": int(time.time() * 1000),
            })
        logger.log_event("INFO", "BOOK_SNAPSHOT", self.active_ticker, f"Bids: {len(bids)} | Asks: {len(asks)}")

    def _handle_price_change(self, data: dict):
        if not state_manager: return
        state = state_manager.get_or_create(self.active_ticker)
        
        changes = data.get("price_changes", [])
        for pc in changes:
            price, side = pc.get("price", "0"), pc.get("side", "").upper()
            if side == "BUY":
                state.apply_ticker({"yes_bid_dollars": price, "ts_ms": int(time.time() * 1000)})
            elif side == "SELL":
                state.apply_ticker({"yes_ask_dollars": price, "ts_ms": int(time.time() * 1000)})

    def _handle_last_trade(self, data: dict):
        if not state_manager: return
        state = state_manager.get_or_create(self.active_ticker)
        state.apply_ticker({"price_dollars": data.get("price", "0"), "ts_ms": int(time.time() * 1000)})

    def _on_error(self, ws, error):
        logger.log_event("ERROR", "WSS_ERROR", self.active_ticker, str(error))

    def _on_close(self, ws, close_status_code, close_msg):
        logger.log_event("WARNING", "WSS_CLOSED", self.active_ticker, f"Code: {close_status_code} | Msg: {close_msg}")

    def stop(self):
        self._running = False
        if self.ws: self.ws.close()
