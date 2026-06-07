"""
orderbook_imbalance.py
Kalshi Agent v3.0 — Microstructure Edge
Calculates Order Book Imbalance (OBI) from live WebSocket data already
flowing into market_state.py. Slot this into context_builder.py output.

OBI = (BidQty - AskQty) / (BidQty + AskQty)
Range: -1.0 (all sell pressure) to +1.0 (all buy pressure)
Edge: Heavy skew predicts short-term direction BEFORE price moves.
"""

from decimal import Decimal, InvalidOperation


class OrderBookAnalyzer:
    """
    Reads the yes_levels/no_levels already stored in MarketState
    and produces a clean imbalance signal for the prompt.
    """

    # Thresholds tuned for Kalshi's thin prediction market books
    STRONG_BUY_THRESHOLD  =  0.35   # Strong buy-side pressure
    STRONG_SELL_THRESHOLD = -0.35   # Strong sell-side pressure
    NEUTRAL_BAND          =  0.15   # Inside this = no meaningful signal

    def __init__(self, depth: int = 5):
        """
        depth: how many price levels to sum (top-N of the book).
        Kalshi books are thin — 5 levels captures most of the real signal.
        """
        self.depth = depth

    def _safe_decimal(self, val) -> Decimal:
        try:
            return Decimal(str(val))
        except (InvalidOperation, TypeError):
            return Decimal("0")

    def calculate_obi(self, yes_levels: list, no_levels: list) -> dict:
        """
        yes_levels: list of (price, size) tuples — bids (YES buyers)
        no_levels:  list of (price, size) tuples — asks (NO buyers / YES sellers)

        Returns a dict ready to be injected into the context prompt.
        """
        if not yes_levels and not no_levels:
            return self._empty_result("No orderbook data available")

        # Sum quantity across top-N levels
        bid_qty = sum(
            self._safe_decimal(lvl[1])
            for lvl in yes_levels[:self.depth]
        )
        ask_qty = sum(
            self._safe_decimal(lvl[1])
            for lvl in no_levels[:self.depth]
        )

        total = bid_qty + ask_qty
        if total == Decimal("0"):
            return self._empty_result("Zero liquidity on both sides")

        obi = float((bid_qty - ask_qty) / total)

        # Interpret the signal
        if obi >= self.STRONG_BUY_THRESHOLD:
            label    = "STRONG_BUY_PRESSURE"
            edge     = "YES"
            readable = f"Buy wall dominates ({obi:+.2f}) — market expects YES"
        elif obi <= self.STRONG_SELL_THRESHOLD:
            label    = "STRONG_SELL_PRESSURE"
            edge     = "NO"
            readable = f"Sell wall dominates ({obi:+.2f}) — market expects NO"
        elif abs(obi) <= self.NEUTRAL_BAND:
            label    = "NEUTRAL"
            edge     = "NONE"
            readable = f"Book balanced ({obi:+.2f}) — no directional edge"
        else:
            label    = "MILD_IMBALANCE"
            edge     = "YES" if obi > 0 else "NO"
            readable = f"Mild {'buy' if obi > 0 else 'sell'} skew ({obi:+.2f})"

        return {
            "obi_score":       round(obi, 4),
            "obi_label":       label,
            "obi_edge":        edge,
            "obi_readable":    readable,
            "bid_depth_qty":   float(bid_qty),
            "ask_depth_qty":   float(ask_qty),
            "levels_analyzed": min(self.depth, max(len(yes_levels), len(no_levels))),
            "data_quality":    "FULL" if (bid_qty > 0 and ask_qty > 0) else "PARTIAL",
        }

    def build_prompt_block(self, yes_levels: list, no_levels: list) -> str:
        """
        Returns a formatted string block ready to append to your
        existing context_builder prompt sections.
        """
        result = self.calculate_obi(yes_levels, no_levels)

        if result.get("data_quality") == "UNAVAILABLE":
            return ""

        lines = [
            "## ORDERBOOK MICROSTRUCTURE (Live)",
            f"Order Book Imbalance (OBI): {result['obi_score']:+.4f}",
            f"Signal: {result['obi_label']}",
            f"Interpretation: {result['obi_readable']}",
            f"Bid-side depth (top-{result['levels_analyzed']}): {result['bid_depth_qty']:.1f} contracts",
            f"Ask-side depth (top-{result['levels_analyzed']}): {result['ask_depth_qty']:.1f} contracts",
            "",
            "INSTRUCTION: If OBI_EDGE aligns with your macro signal, increase confidence by 5-8 points.",
            "INSTRUCTION: If OBI_EDGE CONTRADICTS your macro signal, treat as a warning — cap confidence at 70.",
        ]
        return "\n".join(lines)

    def _empty_result(self, reason: str) -> dict:
        return {
            "obi_score":       0.0,
            "obi_label":       "UNAVAILABLE",
            "obi_edge":        "NONE",
            "obi_readable":    reason,
            "data_quality":    "UNAVAILABLE",
        }


# Module singleton
obi_analyzer = OrderBookAnalyzer(depth=5)
