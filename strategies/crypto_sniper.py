import os
import logging
from strategies.base_strategy import BaseStrategy
from engine.cro_auditor import audit_signal
from data.alpha_clients.moa_debate import moa_brain
from data.alpha_clients.binance_client import binance_client
from data.alpha_clients.kalshi_orderbook import kalshi_ob_client

logger = logging.getLogger("CRYPTO_SNIPER")


class CryptoSniperEdge(BaseStrategy):

    def __init__(self):
        super().__init__()
        self._active_ticker = None

    @property
    def name(self) -> str:
        return "CRYPTO_SNIPER"

    @property
    def ticker_prefix(self) -> str:
        return self._active_ticker or "KXBTC-DYNAMIC"

    def get_prewarm_time(self) -> str:
        return "15:50:00"

    def get_execute_time(self) -> str:
        return "15:55:00"

    def is_active_today(self) -> bool:
        return os.getenv("CRYPTO_ACTIVE", "false").lower() == "true"

    def pre_warm(self):
        # Step 1: Resolve ticker safely before calling super
        try:
            logger.info(f"[{self.name}] Resolving dynamic Kalshi BTC ticker...")
            # TODO: Hit Kalshi REST API to find active daily BTC ticker
            # For now use placeholder — replace when Kalshi is funded
            self._active_ticker = os.getenv("CRYPTO_TICKER", "KXBTC-PLACEHOLDER")
            logger.info(f"[{self.name}] Ticker resolved: {self._active_ticker}")
        except Exception as e:
            logger.error(f"[{self.name}] Ticker resolution failed: {e}")
            return  # Abort — do not call super() with no ticker

        # Step 2: BaseStrategy handles signal generation and caching
        super().pre_warm()

    def build_context(self) -> dict:
        """
        Returns context dict for generate_signal().
        Must return dict — never a signal dict.
        Empty dict {} signals BaseStrategy to abort gracefully.
        """
        if not self._active_ticker:
            logger.error(f"[{self.name}] No ticker — returning empty context.")
            return {}

        # 1. Data ingestion
        l2_depth = {}
        live_cost = {}
        try:
            from data.alpha_clients.binance_client import binance_client
            from data.alpha_clients.kalshi_orderbook import kalshi_ob_client
            l2_depth = binance_client.get_crypto_depth("BTC-USD")
            live_cost = kalshi_ob_client.get_orderbook(self._active_ticker)
            logger.info(f"[{self.name}] Data ingestion OK")
        except Exception as e:
            logger.error(f"[{self.name}] Data ingestion failed: {e}")
            # Continue with empty data — MoA will note data gap

        # 2. MoA debate pipeline
        moa_signal = {}
        try:
            from data.alpha_clients.moa_debate import moa_brain
            moa_signal = moa_brain.execute_debate(
                ticker=self._active_ticker,
                macro_data=l2_depth,
                orderbook_data=live_cost,
            )
            logger.info(f"[{self.name}] MoA debate complete")
        except Exception as e:
            logger.error(f"[{self.name}] MoA pipeline failed: {e}")
            # Return context without MoA signal — brain will generate independently

        # 3. Build context dict for BaseStrategy
        return {
            "ticker":       self._active_ticker,
            "l2_depth":     l2_depth,
            "live_cost":    live_cost,
            "moa_signal":   moa_signal,
            "bls_history":  [],
            "fred_history": [],
            "mom_direction": "NEUTRAL",
            "prompt": (
                "You are an elite crypto prediction market analyst.\n"
                "Analyze whether Bitcoin will close UP or DOWN today.\n\n"
                f"TICKER: {self._active_ticker}\n"
                f"COINBASE L2 DEPTH: {l2_depth}\n"
                f"KALSHI ORDERBOOK: {live_cost}\n"
                f"MOA PRE-ANALYSIS: {moa_signal}\n\n"
                "SIGNAL MAPPING:\n"
                "  BUY_YES = Bitcoin closes HIGHER than current price\n"
                "  BUY_NO  = Bitcoin closes LOWER than current price\n"
                "  WATCH   = No clear edge\n\n"
                "CONFIDENCE ANCHORS:\n"
                "  90-100: L2 depth strongly one-sided AND Kalshi mispriced >15 cents\n"
                "  75-89:  Clear directional signal from depth or MoA\n"
                "  65-74:  Some signal but conflicting data\n"
                "  Below 65: No edge — output WATCH\n\n"
                "Output ONLY valid JSON:\n"
                "{\n"
                '  "signal": "BUY_YES" or "BUY_NO" or "WATCH",\n'
                '  "confidence": integer 0-100,\n'
                '  "suggested_entry_dollars": "0.XX",\n'
                '  "risk_flag": "LOW" or "MEDIUM" or "HIGH",\n'
                '  "edge_source": "L2_DEPTH" or "ORDERBOOK" or "MOA" or "MIXED",\n'
                '  "reasoning": "2-3 sentences citing specific values"\n'
                "}\n"
                "Entry price must be quoted string 0.01-0.99. Never above 0.85."
            ),
        }
