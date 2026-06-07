"""
vrp_analyzer.py
Kalshi Agent v3.0 — Volatility Risk Premium Edge
Compares VIX (implied vol) against realized S&P 500 volatility.

The structural edge: options market consistently OVERPRICES volatility.
When VIX >> realized vol → market is pricing in fear that won't materialize
→ fade the fear → go LONG equities / BUY_YES on S&P up days.

Wires directly into DailyEquitiesHunter.build_context() which already
fetches VIX and SPX data via yfinance_client.
"""

import math
from decimal import Decimal


class VRPAnalyzer:
    """
    Volatility Risk Premium calculator.
    All inputs come from yfinance_client.get_snapshot() which you already call.
    No new dependencies, no new API keys.
    """

    # Annualization factor: sqrt(252 trading days)
    ANNUALIZATION = math.sqrt(252)

    # VRP thresholds (percentage points of annualized vol)
    STRONG_PREMIUM_THRESHOLD = 5.0    # VIX > realized + 5pts → strong fear premium
    MILD_PREMIUM_THRESHOLD   = 2.5    # VIX > realized + 2.5pts → mild premium
    DISCOUNT_THRESHOLD       = -2.0   # VIX < realized - 2pts → market underpricing risk

    def calculate_realized_vol(self, price_history: list) -> float:
        """
        Calculates annualized realized volatility from a list of daily close prices.
        Needs at least 5 prices for a meaningful reading (uses log returns).

        price_history: list of floats, newest first (matches yfinance output shape)
        Returns: annualized realized vol as a percentage (e.g. 14.2 means 14.2%)
        """
        if len(price_history) < 5:
            return 0.0

        # Work oldest-to-newest for log return calculation
        prices = list(reversed(price_history))

        log_returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0 and prices[i] > 0:
                log_returns.append(math.log(prices[i] / prices[i - 1]))

        if len(log_returns) < 2:
            return 0.0

        n    = len(log_returns)
        mean = sum(log_returns) / n
        variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)
        daily_vol = math.sqrt(variance)

        # Annualize and convert to percentage
        return round(daily_vol * self.ANNUALIZATION * 100, 2)

    def calculate_vrp(self, vix_level: float, realized_vol: float) -> dict:
        """
        VIX level: the spot VIX reading (already a percentage, e.g. 18.5)
        realized_vol: output of calculate_realized_vol()

        Returns a signal dict with a ready-to-inject prompt block.
        """
        if vix_level <= 0 or realized_vol <= 0:
            return self._empty_result("Insufficient data for VRP calculation")

        vrp = round(vix_level - realized_vol, 2)

        # Classify the premium
        if vrp >= self.STRONG_PREMIUM_THRESHOLD:
            label     = "STRONG_FEAR_PREMIUM"
            direction = "BULLISH"
            readable  = (
                f"VIX ({vix_level:.1f}) is {vrp:.1f}pts above realized vol "
                f"({realized_vol:.1f}%). Market is overpricing fear. "
                f"Structural edge: FADE THE FEAR → BUY_YES on upside."
            )
            confidence_adjustment = +7

        elif vrp >= self.MILD_PREMIUM_THRESHOLD:
            label     = "MILD_FEAR_PREMIUM"
            direction = "SLIGHTLY_BULLISH"
            readable  = (
                f"VIX ({vix_level:.1f}) is {vrp:.1f}pts above realized vol "
                f"({realized_vol:.1f}%). Mild fear premium — modest upside edge."
            )
            confidence_adjustment = +3

        elif vrp <= self.DISCOUNT_THRESHOLD:
            label     = "COMPLACENCY_RISK"
            direction = "BEARISH"
            readable  = (
                f"VIX ({vix_level:.1f}) is BELOW realized vol ({realized_vol:.1f}%). "
                f"Market underpricing risk. Complacency — elevated downside risk."
            )
            confidence_adjustment = -5

        else:
            label     = "NEUTRAL_VRP"
            direction = "NEUTRAL"
            readable  = (
                f"VIX ({vix_level:.1f}) vs realized ({realized_vol:.1f}%). "
                f"Premium of {vrp:+.1f}pts — no strong structural edge."
            )
            confidence_adjustment = 0

        return {
            "vix_level":              vix_level,
            "realized_vol":           realized_vol,
            "vrp":                    vrp,
            "vrp_label":              label,
            "vrp_direction":          direction,
            "vrp_readable":           readable,
            "confidence_adjustment":  confidence_adjustment,
            "data_quality":           "FULL",
        }

    def build_prompt_block(
        self,
        vix_snapshot: dict,
        spx_price_history: list
    ) -> str:
        """
        vix_snapshot: output of yfinance_client.get_snapshot("^VIX")
                      — you already call this in DailyEquitiesHunter
        spx_price_history: list of recent SPX closing prices (floats)
                           Pull from yfinance history — see integration note below

        Returns a formatted string block for the prompt.
        """
        try:
            vix_level = float(vix_snapshot.get("price", 0))
        except (ValueError, TypeError):
            return "## VRP SIGNAL\nUnavailable — VIX parse error\n"

        realized = self.calculate_realized_vol(spx_price_history)
        if realized == 0.0:
            return "## VRP SIGNAL\nUnavailable — insufficient price history\n"

        result = self.calculate_vrp(vix_level, realized)

        lines = [
            "## VOLATILITY RISK PREMIUM (Structural Edge)",
            f"Implied Vol (VIX):      {result['vix_level']:.1f}%",
            f"Realized Vol (20d SPX): {result['realized_vol']:.1f}%",
            f"VRP Spread:             {result['vrp']:+.1f} percentage points",
            f"Signal:                 {result['vrp_label']}",
            f"",
            f"INTERPRETATION: {result['vrp_readable']}",
            f"",
            f"CONFIDENCE RULE: Apply {result['confidence_adjustment']:+d} points to your",
            f"confidence score if your directional signal matches VRP direction ({result['vrp_direction']}).",
            f"Do NOT override your macro signal — use VRP as a confidence modifier only.",
        ]
        return "\n".join(lines)

    def _empty_result(self, reason: str) -> dict:
        return {
            "vrp":          0.0,
            "vrp_label":    "UNAVAILABLE",
            "vrp_direction":"NEUTRAL",
            "vrp_readable": reason,
            "confidence_adjustment": 0,
            "data_quality": "UNAVAILABLE",
        }


# Module singleton
vrp_analyzer = VRPAnalyzer()


if __name__ == "__main__":
    # Quick test with synthetic data
    print("[*] Testing VRP Analyzer...")

    fake_vix = {"price": "22.5"}
    # Simulate 21 days of SPX prices with mild downtrend + noise
    import random
    random.seed(42)
    price = 5100.0
    history = []
    for _ in range(21):
        price *= (1 + random.gauss(-0.001, 0.008))
        history.insert(0, price)  # newest first

    block = vrp_analyzer.build_prompt_block(fake_vix, history)
    print(block)
