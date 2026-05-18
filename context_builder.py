"""
context_builder.py
Kalshi Agent v2.3 — Signal Context Assembler
Improvements over v2.1:
- Pre-calculates CPI month-over-month change and trend direction
- Market-specific prompt framing with exact question context
- Entry price explicitly constrained to 0.01-0.99 probability range
- Confidence calibration guidance added to prompt
- Dynamic prompt block appending — no N/A fields
"""

from decimal import Decimal, InvalidOperation
from config import cfg

try:
    from output.agent_logger import logger
    from state.market_state import state_manager
    from data.fred_client import fred_client
    from data.bls_client import bls_client
    from data.news_client import news_client
except ImportError as e:
    print(f"[!] Import error in context_builder: {e}")

try:
    from data.metaculus_client import metaculus_client
    METACULUS_AVAILABLE = True
except ImportError:
    METACULUS_AVAILABLE = False


def _calc_mom_change(fred_data: list) -> dict:
    """
    Pre-calculates month-over-month CPI change from FRED data.
    Returns dict with latest, prior, mom_change, trend_direction.
    Saves the model from having to do math on raw index values.
    """
    result = {
        "latest_value":    None,
        "prior_value":     None,
        "mom_change":      None,
        "mom_pct":         None,
        "trend_direction": "UNKNOWN",
        "consecutive_up":  0,
    }

    if not fred_data or len(fred_data) < 2:
        return result

    try:
        latest = Decimal(str(fred_data[0].get("value", "0")))
        prior  = Decimal(str(fred_data[1].get("value", "0")))

        if prior > Decimal("0"):
            mom_change = latest - prior
            mom_pct    = (mom_change / prior) * Decimal("100")

            result["latest_value"] = str(latest)
            result["prior_value"]  = str(prior)
            result["mom_change"]   = str(round(mom_change, 3))
            result["mom_pct"]      = str(round(mom_pct, 4))
            result["trend_direction"] = "UP" if mom_change > 0 else "DOWN" if mom_change < 0 else "FLAT"

            # Count consecutive months in same direction
            consecutive = 0
            for i in range(len(fred_data) - 1):
                try:
                    v1 = Decimal(str(fred_data[i].get("value", "0")))
                    v2 = Decimal(str(fred_data[i+1].get("value", "0")))
                    diff = v1 - v2
                    if result["trend_direction"] == "UP" and diff > 0:
                        consecutive += 1
                    elif result["trend_direction"] == "DOWN" and diff < 0:
                        consecutive += 1
                    else:
                        break
                except InvalidOperation:
                    break
            result["consecutive_up"] = consecutive

    except (InvalidOperation, TypeError):
        pass

    return result


def build_context() -> dict:
    """
    Assembles complete market context and returns fully formatted
    prompt ready for the local Ollama signal engine.
    """
    ticker = cfg.TARGET_TICKER
    if not ticker:
        logger.log_event("ERROR", "CONTEXT_BUILDER", "NONE", "No TARGET_TICKER defined.")
        return {}

    # 1. Fetch Live Market State
    snapshot = state_manager.get_or_create(ticker).get_snapshot_dict()

    # 2. Extract Pricing — Decimal Enforcement
    try:
        kalshi_ask  = Decimal(str(snapshot.get("yes_ask")    or "0"))
        kalshi_bid  = Decimal(str(snapshot.get("yes_bid")    or "0"))
        last_price  = Decimal(str(snapshot.get("last_price") or "0"))
        spread      = kalshi_ask - kalshi_bid
    except InvalidOperation:
        kalshi_ask = kalshi_bid = last_price = Decimal("0")
        spread = Decimal("0")

    if last_price > Decimal("0"):
        implied_prob = int(last_price * Decimal("100"))
    elif kalshi_bid > Decimal("0") and kalshi_ask > Decimal("0"):
        implied_prob = int(((kalshi_bid + kalshi_ask) / Decimal("2")) * Decimal("100"))
    else:
        implied_prob = 50  # Neutral default

    # 3. Fetch External Data
    fred_data      = fred_client.get_series("CPIAUCSL", limit=6)
    bls_data       = bls_client.get_series("CUSR0000SA0", limit=6)
    news_data      = news_client.get_sentiment(ticker)
    metaculus_data = metaculus_client.get_forecast(ticker) \
        if METACULUS_AVAILABLE else {"questions": [], "avg_probability": None}

    # 4. Pre-calculate MoM trend — saves model from doing index math
    mom = _calc_mom_change(fred_data)

    # 5. Divergence Flag
    meta_prob = metaculus_data.get("avg_probability")
    if meta_prob is not None and kalshi_ask > Decimal("0"):
        try:
            diff = abs(Decimal(str(meta_prob)) - kalshi_ask)
            if diff > Decimal("0.15"):
                divergence_flag = "HIGH"
            elif diff > Decimal("0.08"):
                divergence_flag = "MEDIUM"
            else:
                divergence_flag = "LOW"
        except InvalidOperation:
            divergence_flag = "UNDETECTABLE"
    else:
        divergence_flag = "UNDETECTABLE (single source)"

    # 6. Build Prompt Dynamically
    prompt_sections = []

    # ── System Role ───────────────────────────────────────────
    prompt_sections.append(
        "You are a quantitative prediction market analyst.\n"
        "Your job is to find mispricings between economic data and market prices.\n"
        "Be precise. Be calibrated. Only express high confidence when data strongly supports it.\n\n"
        "CONFIDENCE CALIBRATION GUIDE:\n"
        "  90-100: Near-certain edge — multiple strong signals align\n"
        "  75-89:  Strong edge — clear data supports position\n"
        "  65-74:  Moderate edge — directional signal but some uncertainty\n"
        "  50-64:  Weak edge — output HOLD or WATCH\n"
        "  Below 50: No edge — output WATCH"
    )

    # ── Market Question ───────────────────────────────────────
    market_lines = [
        "## MARKET BEING ANALYZED",
        f"Question: Will U.S. CPI inflation be positive (above 0%) month-over-month?",
        f"Market Ticker: {ticker}",
        f"Current Market Price: {str(kalshi_ask)} (market implies {implied_prob}% probability of YES)",
        f"Bid/Ask Spread: {str(spread)}",
        "",
        "PRICE INTERPRETATION:",
        "  - Price of 0.60 means market thinks 60% chance the answer is YES",
        "  - Price of 0.40 means market thinks 40% chance the answer is YES",
        "  - Your edge = where you think true probability differs from market price",
    ]
    prompt_sections.append("\n".join(market_lines))

    # ── FRED Macro Data ───────────────────────────────────────
    if fred_data and mom["mom_change"] is not None:
        fred_lines = [
            "## CPI HISTORICAL DATA (FRED — CPIAUCSL)",
            f"Latest CPI Index Value: {mom['latest_value']} ({fred_data[0].get('date', '?')})",
            f"Prior Month: {mom['prior_value']} ({fred_data[1].get('date', '?')})",
            f"Month-over-Month Change: {mom['mom_change']} index points ({mom['mom_pct']}%)",
            f"Trend Direction: {mom['trend_direction']} ({mom['consecutive_up']} consecutive months)",
            f"6-Month History: " + ", ".join([f"{d.get('date','?')}: {d.get('value','?')}" for d in fred_data]),
        ]
        prompt_sections.append("\n".join(fred_lines))
    elif fred_data:
        history_str = ", ".join([f"{d.get('date','?')}: {d.get('value','?')}" for d in fred_data])
        prompt_sections.append(f"## CPI HISTORICAL DATA (FRED)\n6-Month History: {history_str}")

    # ── BLS Settlement Data ───────────────────────────────────
    if bls_data:
        bls_str = ", ".join([f"{d.get('period','?')}: {d.get('value','?')}" for d in bls_data])
        prompt_sections.append(f"## BLS SETTLEMENT DATA (CPI-U)\nRecent Releases: {bls_str}")

    # ── Metaculus Crowd Forecast ──────────────────────────────
    if metaculus_data and metaculus_data.get("questions"):
        meta_lines = [
            "## CROWD FORECAST (METACULUS)",
            f"Community Average Probability: {meta_prob}",
            f"Based on {len(metaculus_data.get('questions'))} active questions",
        ]
        if meta_prob is not None:
            market_price_float = float(str(kalshi_ask)) if kalshi_ask > 0 else 0.5
            crowd_diff = round(float(str(meta_prob)) - market_price_float, 3)
            meta_lines.append(f"Crowd vs Market Divergence: {crowd_diff:+.3f}")
        prompt_sections.append("\n".join(meta_lines))

    # ── Sentiment ─────────────────────────────────────────────
    if news_data and news_data.get("headlines"):
        headlines_str = " | ".join(news_data.get("headlines", [])[:5])
        news_lines = [
            "## NEWS SENTIMENT (GDELT)",
            f"Top Headlines: {headlines_str}",
            f"Sentiment Score: {news_data.get('sentiment_score')} (-1.0=bearish, +1.0=bullish)",
            f"Raw GDELT Tone: {news_data.get('gdelt_tone')}",
        ]
        prompt_sections.append("\n".join(news_lines))

    # ── Divergence Summary ────────────────────────────────────
    prompt_sections.append(
        f"## DIVERGENCE ANALYSIS\n"
        f"Market Price vs External Sources: {divergence_flag}"
    )

    # ── Output Format ─────────────────────────────────────────
    prompt_sections.append(
        "## REQUIRED OUTPUT\n"
        "Respond ONLY with this exact JSON — no text before or after:\n"
        "{\n"
        '  "signal": "BUY_YES" or "BUY_NO" or "HOLD" or "WATCH",\n'
        '  "confidence": integer 0-100,\n'
        '  "suggested_entry_dollars": "0.XX" (MUST be between 0.01 and 0.99 — this is a PROBABILITY PRICE not a dollar amount),\n'
        '  "risk_flag": "LOW" or "MEDIUM" or "HIGH",\n'
        '  "edge_source": "FRED" or "BLS" or "METACULUS" or "SENTIMENT" or "ORDERBOOK" or "TREND",\n'
        '  "reasoning": "2-3 sentences explaining your edge"\n'
        "}\n\n"
        "ENTRY PRICE RULES:\n"
        "  BUY_YES: suggested_entry_dollars should be current ask price or lower (e.g. 0.55)\n"
        "  BUY_NO: suggested_entry_dollars should be 1 minus ask price (e.g. 0.45)\n"
        "  HOLD/WATCH: suggested_entry_dollars should be current mid price\n"
        "  NEVER output a value above 0.99 or below 0.01"
    )

    final_prompt = "\n\n".join(prompt_sections)

    return {
        "ticker":          ticker,
        "event_name":      ticker,
        "release_ts":      "Pending",
        "fred_history":    fred_data,
        "bls_history":     bls_data,
        "kalshi_snapshot": snapshot,
        "metaculus":       metaculus_data,
        "news":            news_data,
        "divergence_flag": divergence_flag,
        "mom_analysis":    mom,
        "prompt":          final_prompt,
    }


if __name__ == "__main__":
    cfg.TARGET_TICKER = "CPI"
    print("[*] Building Context...")
    result = build_context()
    print("\n[ASSEMBLED PROMPT]\n")
    print(result.get("prompt", "FAILED"))
