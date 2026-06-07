"""
daily_harvester.py
Kalshi Agent v3.0 — Background Paper Trading Loop
Runs every hour around the clock, generating paper signals for SPX/VIX
even when no live events are scheduled.

PURPOSE: Builds a continuous track record of AI signal quality so you
have real performance data before risking capital on equities strategies.
Logs everything to the Ghost Book — grade it WIN/LOSS after close.

Run standalone: python3 engine/daily_harvester.py
Or call run_harvest_cycle() from a scheduler.
"""
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import cfg
from output.agent_logger import logger
from data.yfinance_client import yfinance_client
from data.rss_client import rss_client
from engine.signal_engine import generate_signal
from engine.ghost_book import execute_paper_trade


def run_harvest_cycle():
    """
    Single harvest cycle:
    1. Fetch live SPX + VIX data
    2. Fetch macro sentiment from RSS (replaces dead news_client)
    3. Generate AI signal via signal_engine
    4. Log to Ghost Book as paper trade
    """
    logger.log_event("INFO", "HARVESTER_CYCLE", "SYSTEM",
                     "Starting macro data harvest.")

    # 1. Market data
    market_data = yfinance_client.get_market_context()
    spx         = market_data.get("spx", {})
    vix         = market_data.get("vix", {})
    spx_price   = spx.get("price", "UNKNOWN")
    vix_price   = vix.get("price", "UNKNOWN")
    spx_change  = spx.get("pct_change", "0")

    # 2. Sentiment via RSS (news_client is disabled — rss_client is live)
    news_data   = rss_client.get_sentiment("CPI")
    sentiment   = news_data.get("sentiment_score", 0)

    # 3. Build prompt for signal engine
    ai_prompt = (
        f"You are a quantitative macro analyst. "
        f"S&P 500: {spx_price} ({spx_change}% today). "
        f"VIX: {vix_price}. "
        f"RSS Sentiment Score: {sentiment}. "
        f"Generate a paper-trading signal for the daily equities market. "
        f"Respond ONLY with valid JSON: "
        f'{{"signal": "BUY_YES"|"BUY_NO"|"WATCH", '
        f'"confidence": 0-100, '
        f'"suggested_entry_dollars": "0.XX", '
        f'"risk_flag": "LOW"|"MEDIUM"|"HIGH", '
        f'"edge_source": "VIX"|"TREND"|"SENTIMENT", '
        f'"reasoning": "2 sentences max"}}'
    )

    context = {
        "ticker": "SPX_DAILY",
        "prompt": ai_prompt
    }

    try:
        signal_output = generate_signal(context)

        sig      = signal_output.get("signal",    "WATCH")
        conf     = signal_output.get("confidence", 0)
        reason   = signal_output.get("reasoning", "No reasoning provided.")
        edge     = signal_output.get("edge_source", "UNKNOWN")
        risk     = signal_output.get("risk_flag",   "MEDIUM")

        # 4. Log to Ghost Book via the shared execute_paper_trade function
        # Uses cfg.DB_PATH — no hardcoded paths
        execute_paper_trade(
            strategy   = "DAILY_HARVESTER",
            ticker     = "SPX_DAILY",
            signal     = sig,
            confidence = conf,
            entry_price = str(spx_price),
            contracts  = 0,   # Paper only — no real sizing
            edge_source = edge,
            reasoning  = reason
        )

        logger.log_event(
            "INFO", "HARVESTER_SIGNAL", "SPX_DAILY",
            f"{sig} @ {spx_price} | conf={conf}% | edge={edge}"
        )

    except Exception as e:
        logger.log_event("ERROR", "HARVESTER_SIGNAL_FAIL", "SPX_DAILY",
                         f"Inference failed: {e}")

    logger.log_event("INFO", "HARVESTER_SLEEP", "SYSTEM",
                     "Cycle complete. Sleeping 60 minutes.")


if __name__ == "__main__":
    while True:
        try:
            run_harvest_cycle()
        except Exception as e:
            logger.log_event("CRITICAL", "HARVESTER_FAULT", "SYSTEM", str(e))
        time.sleep(3600)
