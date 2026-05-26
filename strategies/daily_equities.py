"""
daily_equities.py
Kalshi Agent v2.5 — Phase 2: Daily Equities Hunter
Snipes the S&P 500 daily close at 15:30 ET using yfinance and VIX data.
"""

import os
import datetime
from strategies.base_strategy import BaseStrategy

class DailyEquitiesHunter(BaseStrategy):
    @property
    def name(self) -> str:
        return "EQUITIES_HUNTER"

    @property
    def ticker_prefix(self) -> str:
        return "KXINTRADAY"

    def get_prewarm_time(self) -> str:
        return "15:25:00"

    def get_execute_time(self) -> str:
        return "15:30:00"

    def is_active_today(self) -> bool:
        if os.getenv("EQUITIES_ACTIVE", "true").lower() == "false":
            return False
            
        today = datetime.date.today()
        if today.weekday() >= 5:
            return False
            
        # Suppress on FOMC days — Fed moves markets violently
        try:
            from data.fed_client import fed_client
            if fed_client.get_fed_context().get("is_fomc_today"):
                return False
        except Exception:
            pass  # If fed_client fails, run equities anyway
            
        return True

    def build_context(self) -> dict:
        from data.yfinance_client import yfinance_client
        from data.rss_client import rss_client
        from decimal import Decimal

        market_ctx = yfinance_client.get_market_context()
        spx        = market_ctx.get("spx", {})
        vix        = market_ctx.get("vix", {})
        news_data  = rss_client.get_sentiment("CPI")

        # VIX regime
        try:
            vix_price = Decimal(str(vix.get("price", "20")))
            if vix_price > Decimal("30"):
                vix_regime = "EXTREME_FEAR (VIX > 30)"
            elif vix_price > Decimal("20"):
                vix_regime = "ELEVATED_FEAR (VIX 20-30)"
            elif vix_price > Decimal("15"):
                vix_regime = "NEUTRAL (VIX 15-20)"
            else:
                vix_regime = "COMPLACENCY (VIX < 15)"
        except Exception:
            vix_regime = "UNKNOWN"

        # SPX trend
        try:
            pct = Decimal(str(spx.get("pct_change", "0")))
            spx_trend = (
                f"STRONG_UP (+{pct}%)" if pct > Decimal("0.5") else
                f"SLIGHT_UP (+{pct}%)" if pct > Decimal("0") else
                f"SLIGHT_DOWN ({pct}%)" if pct > Decimal("-0.5") else
                f"STRONG_DOWN ({pct}%)"
            )
        except Exception:
            spx_trend = "UNKNOWN"

        prompt_sections = [
            "You are a quantitative prediction market analyst "
            "specializing in intraday US equity markets.\n"
            "Analyze whether the S&P 500 will close UP or DOWN "
            "from its current price before the 4:00 PM ET close.\n\n"
            "CONFIDENCE CALIBRATION:\n"
            "  90-100: Extreme VIX + strong trend alignment\n"
            "  75-89:  Clear directional signal\n"
            "  65-74:  Some uncertainty\n"
            "  Below 65: No edge — output WATCH",

            f"## S&P 500 INTRADAY DATA\n"
            f"Current Price: {spx.get('price')}\n"
            f"Previous Close: {spx.get('prev_close')}\n"
            f"Intraday Range: {spx.get('day_low')} — {spx.get('day_high')}\n"
            f"Intraday Trend: {spx_trend}\n"
            f"Volume: {spx.get('volume')}",

            f"## VOLATILITY (VIX)\n"
            f"VIX Level: {vix.get('price')}\n"
            f"VIX Regime: {vix_regime}\n"
            f"VIX Daily Change: {vix.get('pct_change')}%",
        ]

        if news_data and news_data.get("headlines"):
            headlines = " | ".join(news_data.get("headlines", [])[:3])
            prompt_sections.append(
                f"## MACRO SENTIMENT\n"
                f"Sentiment Score: {news_data.get('sentiment_score')}\n"
                f"Headlines: {headlines}"
            )

        prompt_sections.append(
            "## REQUIRED OUTPUT\n"
            "Respond ONLY with this exact JSON:\n"
            "{\n"
            '  "signal": "BUY_YES" or "BUY_NO" or "WATCH",\n'
            '  "confidence": integer 0-100,\n'
            '  "suggested_entry_dollars": "0.XX",\n'
            '  "risk_flag": "LOW" or "MEDIUM" or "HIGH",\n'
            '  "edge_source": "VIX" or "TREND" or "SENTIMENT" or "MOMENTUM",\n'
            '  "reasoning": "2-3 sentences citing specific values"\n'
            "}\n"
            "ENTRY PRICE must be a quoted string between 0.01 and 0.99.\n"
            "HIGH VIX (>25) = HIGH risk_flag always.\n"
            "Never output entry above 0.85."
        )

        return {
            "ticker":        self.ticker_prefix,
            "strategy_name": self.name,
            "prompt":        "\n\n".join(prompt_sections),
            "mom_direction": "UP" if "UP" in spx_trend else "DOWN",
            "spx":           spx,
            "vix":           vix,
            "vix_regime":    vix_regime,
            "bls_history":   [],
            "fred_history":  [],
        }
