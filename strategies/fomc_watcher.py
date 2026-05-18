"""
fomc_watcher.py
Kalshi Agent v2.5 — Phase 3: FOMC Fed Watcher
Predicts Fed interest rate decisions using 2Y Yields and Press Release NLP.
"""

import os
from strategies.base_strategy import BaseStrategy
from data.fed_client import fed_client

class FOMCWatcher(BaseStrategy):
    @property
    def name(self) -> str:
        return "FOMC_WATCHER"

    @property
    def ticker_prefix(self) -> str:
        return os.getenv("FOMC_TICKER", "KXFED")

    def get_prewarm_time(self) -> str:
        return "13:45:00"

    def get_execute_time(self) -> str:
        return "13:58:00"

    def is_active_today(self) -> bool:
        if os.getenv("FOMC_ACTIVE", "false").lower() != "true":
            return False
            
        ctx = fed_client.get_fed_context()
        return ctx.get("is_fomc_today", False)

    def build_context(self) -> dict:
        fed_data = fed_client.get_fed_context()
        ticker = self.ticker_prefix

        prompt = (
            "You are an elite quantitative macro analyst predicting Kalshi interest rate markets.\n"
            "The FOMC is releasing its rate decision RIGHT NOW.\n\n"
            f"CURRENT FED FUNDS RATE: {fed_data.get('fed_funds_rate')}%\n"
            f"2-YEAR TREASURY YIELD: {fed_data.get('two_year_yield')}% (5-Day Trend: {fed_data.get('yield_trend')}, Change: {fed_data.get('yield_5d_change')}%)\n"
            f"30-DAY INTER-MEETING YIELD CHANGE: {fed_data.get('yield_since_last_fomc')}%\n"
            f"PRESS RELEASE TONE: {fed_data.get('tone_label')} (Score: {fed_data.get('tone_score')})\n"
            f"PRESS RELEASE HEADLINE: {fed_data.get('press_release_title')}\n\n"
            "CALIBRATION RULES FOR THIS MARKET:\n"
            "- BUY_YES = Betting the Fed HOLDS rates at this meeting.\n"
            "- BUY_NO = Betting the Fed CUTS or HIKES at this meeting.\n"
            "- High confidence (>75) requires the Yield Trend and Tone Label to ALIGN (e.g., RISING + HAWKISH).\n"
            "- If data is conflicting, output WATCH or low confidence (<65).\n\n"
            "Output ONLY valid JSON with fields: 'signal' (BUY_YES, BUY_NO, WATCH), 'confidence' (0-100), "
            "'suggested_entry_dollars' (0.XX format, max 0.85), 'risk_flag' (LOW/MEDIUM/HIGH), "
            "'edge_source' (YIELD/TONE/MIXED), and 'reasoning' (2-3 sentences citing exact values)."
        )

        return {
            "ticker": ticker,
            "prompt": prompt,
            "fed_data": fed_data
        }
