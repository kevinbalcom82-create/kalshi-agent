"""
daily_equities.py
Kalshi Agent v2.5 — Phase 2: Daily Equities Hunter
Snipes the S&P 500 daily close at 15:30 ET using yfinance and VIX data.
"""

import os
import datetime
from strategies.base_strategy import BaseStrategy
from engine.vrp_analyzer import vrp_analyzer

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

        try:
            from data.fed_client import fed_client
            if fed_client.get_fed_context().get("is_fomc_today"):
                return False
        except Exception:
            pass

        return True

    def build_context(self) -> dict:
        from data.yfinance_client import yfinance_client
        from data.rss_client import rss_client
        from decimal import Decimal

        market_ctx = yfinance_client.get_market_context()
        spx        = market_ctx.get("spx", {})
        vix        = market_ctx.get("vix", {})
        news_data  = rss_client.get_sentiment("CPI")

        # Fetch SPX price history for VRP realized vol calculation
        spx_history_prices = []
        try:
            import yfinance as yf
            spx_raw = yf.Ticker("^GSPC").history(period="25d")
            spx_history_prices = list(reversed(spx_raw["Close"].tolist()))
        except Exception:
            pass  # VRP block skipped gracefully if this fails

        # VIX regime classification
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

        # SPX trend classification
        try:
            pct = Decimal(str(spx.get("pct_change", "0")))
            spx_trend = (
                f"STRONG_UP (+{pct}%)"   if pct > Decimal("0.5")  else
                f"SLIGHT_UP (+{pct}%)"   if pct > Decimal("0")    else
                f"SLIGHT_DOWN ({pct}%)"  if pct > Decimal("-0.5") else
                f"STRONG_DOWN ({pct}%)"
            )
        except Exception:
            spx_trend = "UNKNOWN"

        prompt_sections = [
            "You are the execution brain of a sovereign quantitative trading fund. "
            "Your mandate is ABSOLUTE CAPITAL PRESERVATION. You do not gamble. You do not guess.\n"
            "Analyze whether the S&P 500 will close UP (BUY_YES) or DOWN (BUY_NO) "
            "from its current price before the 4:00 PM ET close.\n\n"
            "CONFIDENCE CALIBRATION (STRICT):\n"
            "  90-100: Asymmetric edge. Perfect alignment of VIX regime and SPX momentum.\n"
            "  85-89: Strong statistical probability. Clear trend.\n"
            "  Below 85: NO EDGE. You MUST output 'WATCH'. Do not force a trade in chop.",

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

        # Macro sentiment block
        if news_data and news_data.get("headlines"):
            headlines = " | ".join(news_data.get("headlines", [])[:3])
            prompt_sections.append(
                f"## MACRO SENTIMENT\n"
                f"Sentiment Score: {news_data.get('sentiment_score')}\n"
                f"Headlines: {headlines}"
            )

        # VRP block — Volatility Risk Premium structural edge
        vrp_block = vrp_analyzer.build_prompt_block(vix, spx_history_prices)
        if vrp_block:
            prompt_sections.append(vrp_block)

        prompt_sections.append(
            "## REQUIRED OUTPUT\n"
            "Respond ONLY with this exact JSON:\n"
            "{\n"
            '  "signal": "BUY_YES" or "BUY_NO" or "WATCH",\n'
            '  "confidence": integer 0-100,\n'
            '  "suggested_entry_dollars": "0.XX",\n'
            '  "risk_flag": "LOW" or "MEDIUM" or "HIGH",\n'
            '  "edge_source": "VIX" or "TREND" or "SENTIMENT" or "MOMENTUM" or "VRP" or "NONE",\n'
            '  "reasoning": "2-3 sentences. If WATCH, explain why the edge is insufficient."\n'
            "}\n"
            "RULES:\n"
            "1. If confidence < 85, signal MUST be WATCH.\n"
            "2. If VIX is EXTREME_FEAR, risk_flag MUST be HIGH.\n"
            "3. ENTRY PRICE must be a string like '0.55'. Never exceed '0.85'.\n"
            "4. VRP is a confidence MODIFIER only — do not override macro signal direction with it."
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
