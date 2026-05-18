"""
market_state.py
Kalshi Agent v2.2 — State Management Layer
In-memory storage for real-time market data streamed from the WebSocket.
"""
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime
import threading
from config import cfg

class MarketState:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.yes_bid = Decimal("0")
        self.yes_ask = Decimal("0")
        self.price = Decimal("0")
        self.last_update = datetime.utcnow()
        self.snapshot_loaded = False
        self._lock = threading.Lock()

    def apply_snapshot(self, data: dict):
        """Marks the book as initialized when the snapshot arrives."""
        with self._lock:
            self.snapshot_loaded = True
            self.last_update = datetime.utcnow()

    def apply_ticker(self, data: dict):
        """Safely updates price action using Decimal enforcement."""
        with self._lock:
            if "yes_bid_dollars" in data:
                self.yes_bid = Decimal(str(data["yes_bid_dollars"]))
            if "yes_ask_dollars" in data:
                self.yes_ask = Decimal(str(data["yes_ask_dollars"]))
            if "price_dollars" in data:
                self.price = Decimal(str(data["price_dollars"]))
            self.last_update = datetime.utcnow()

    def get_snapshot_dict(self) -> dict:
        """Returns the current market state for the context builder."""
        with self._lock:
            return {
                "ticker": self.ticker,
                "yes_bid": float(self.yes_bid),
                "yes_ask": float(self.yes_ask),
                "price": float(self.price),
                "last_update": self.last_update.isoformat()
            }

class StateManager:
    def __init__(self):
        self.markets: Dict[str, MarketState] = {}
        self.last_snapshot_time: Optional[datetime] = None
        self._lock = threading.Lock()

    def get_or_create(self, ticker: str) -> MarketState:
        """Retrieves the latest state for a ticker, creating it if needed."""
        with self._lock:
            if ticker not in self.markets:
                self.markets[ticker] = MarketState(ticker)
            return self.markets[ticker]

    def dump_state(self) -> dict:
        """Exports current state for engine and context builder evaluation."""
        with self._lock:
            return {
                "orderbooks": {
                    ticker: {
                        "yes_bid": str(market.yes_bid),
                        "yes_ask": str(market.yes_ask),
                        "price": str(market.price),
                        "last_update": market.last_update.isoformat()
                    }
                    for ticker, market in self.markets.items()
                },
                "last_snapshot_time": self.last_snapshot_time.isoformat() if self.last_snapshot_time else None
            }

# Singleton instance to be imported globally by the WebSocket and Main Loop
state_manager = StateManager()
