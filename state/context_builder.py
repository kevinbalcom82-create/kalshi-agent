"""
context_builder.py
Kalshi Agent v2.4 — Signal Context Assembler
Fetches live Kalshi snapshots, polls all Layer 1 data sources, calculates
divergence flags, and dynamically builds the canonical Gemini/Ollama SIGNAL_PROMPT.
"""

from decimal import Decimal, InvalidOperation
from config import cfg

try:
    from output.agent_logger import logger
    from state.market_state import state_manager
    from data.fred_client import fred_client
    from data.bls_client import bls_client
    from data.rss_client import rss_client
    from engine.orderbook_imbalance import obi_analyzer
except ImportError as e:
    print(f"[!] Import error in context_builder: {e}")

def build_context(ticker: str = None) -> dict:
    """
    Assembles the complete state of the market and returns the
    fully formatted prompt ready for the local Ollama signal engine.
    """
    ticker = ticker or cfg.TARGET_TICKER
    if not ticker:
        logger.log_event("ERROR", "CONTEXT_BUILDER", "NONE", "No TARGET_TICKER defined.")
        return {}

    # 1. Fetch Local State (Kalshi/Polymarket)
    kalshi_state = state_manager.get_or_create(ticker)
    snapshot = kalshi_state.get_snapshot_dict()

    # 2. Extract Pricing Safely (Decimal Enforcement)
    try:
        kalshi_ask = Decimal(str(snapshot.get("yes_ask") or "0"))
        kalshi_bid = Decimal(str(snapshot.get("yes_bid") or "0"))
        last_price = Decimal(str(snapshot.get("price") or "0"))
        spread = kalshi_ask - kalshi_bid
    except InvalidOperation:
        kalshi_ask = kalshi_bid = last_price = Decimal("0")
        spread = Decimal("0")

    # Calculate true implied probability (midpoint or last traded)
    if last_price > Decimal("0"):
        implied_prob = int(last_price * Decimal("100"))
    elif kalshi_bid > Decimal("0") and kalshi_ask > Decimal("0"):
        implied_prob = int(((kalshi_bid + kalshi_ask) / Decimal("2")) * Decimal("100"))
    else:
        implied_prob = 0

    # 3. Fetch Layer 1 External Data
    fred_data = fred_client.get_series("CPIAUCSL", limit=6) if 'fred_client' in globals() else []
    bls_data  = bls_client.get_series("CUSR0000SA0", limit=6) if 'bls_client' in globals() else []
    news_data = rss_client.get_sentiment(ticker) if 'rss_client' in globals() else {"headlines": [], "sentiment_score": "NEUTRAL"}

    # 4. Calculate Divergence Flag
    divergence_flag = "UNDETECTABLE (single source)"

    # 5. Build Dynamic Prompt Sections
    prompt_sections = []

    # Base Instructions
    prompt_sections.append(
        "You are a quantitative prediction market analyst for an automated trading agent.\n"
        "Identify pricing inefficiencies between specific economic data (FRED/BLS),\n"
        "news sentiment, and current prediction market prices. You MUST rely on hard numerical data."
    )

    # Event Block
    event_lines = [
        "## UPCOMING EVENT",
        f"Event: {ticker}",
        "Release Time: Pending (Auto-Rollover)"
    ]
    if fred_data:
        latest = fred_data[0].get("value", "Unknown")
        prior  = fred_data[1].get("value", "Unknown") if len(fred_data) > 1 else "Unknown"
        event_lines.append(f"FRED Latest: {latest} (TE unavailable)")
        event_lines.append(f"FRED Prior: {prior}")
        history_str = ", ".join([f"{d.get('date', 'Unknown')}: {d.get('value', '0')}" for d in fred_data])
        event_lines.append(f"Historical Actuals: {history_str}")
    prompt_sections.append("\n".join(event_lines))

    # Kalshi Block
    kalshi_lines = [
        "## MARKET STATE",
        f"Ticker: {ticker}",
        f"Yes Price: {str(kalshi_ask)} (implied {implied_prob}% probability)",
        f"Spread: {str(spread)}",
        f"Divergence Flag: {divergence_flag}"
    ]
    prompt_sections.append("\n".join(kalshi_lines))

    # OBI Block — Order Book Imbalance
    try:
        obi_block = obi_analyzer.build_prompt_block(
            kalshi_state.yes_levels,
            kalshi_state.no_levels
        )
        if obi_block:
            prompt_sections.append(obi_block)
    except Exception as e:
        logger.log_event("WARNING", "OBI_FAIL", ticker, str(e))

    # BLS Block
    if bls_data:
        bls_str   = ", ".join([f"{d.get('period', 'Unknown')}: {d.get('value', '0')}" for d in bls_data])
        bls_lines = [
            "## BLS SETTLEMENT DATA",
            f"Recent Source Data: {bls_str}",
            "CRITICAL: Evaluate this BLS data closely. If it shows an edge against the market, cite 'BLS' as your edge_source."
        ]
        prompt_sections.append("\n".join(bls_lines))

    # Sentiment Block
    if news_data and news_data.get("headlines"):
        headlines_str = " | ".join(news_data.get("headlines", []))
        news_lines = [
            "## MARKET SENTIMENT (RSS)",
            f"Overall Sentiment Score: {news_data.get('sentiment_score')}",
            f"Recent Headlines: {headlines_str}"
        ]
        prompt_sections.append("\n".join(news_lines))

    # Output Block
    output_format = """## OUTPUT
Respond ONLY with valid JSON — no preamble, no markdown. Follow these STRICT reasoning rules:
- REQUIRED: You MUST cite the specific MoM change value or trend in exact numbers (e.g., '+0.147 points').
- REQUIRED: You MUST state exactly what the market is pricing vs what the specific data suggests.
- REQUIRED: You MUST state the specific numerical edge in 1 sentence.

{
  "signal": "BUY_YES" | "BUY_NO" | "HOLD" | "WATCH",
  "confidence": 0-100,
  "suggested_entry_dollars": "0.XX",
  "risk_flag": "LOW" | "MEDIUM" | "HIGH",
  "edge_source": "FRED" | "BLS" | "ORDERBOOK" | "SENTIMENT" | "OBI",
  "reasoning": "Strictly quantitative reasoning comparing exact data points to exact market prices."
}"""
    prompt_sections.append(output_format)

    # Combine all sections
    final_prompt = "\n\n".join(prompt_sections)

    # 6. Return strict dictionary shape
    return {
        "ticker":          ticker,
        "event_name":      ticker,
        "release_ts":      "Pending (Auto-Rollover)",
        "fred_history":    fred_data,
        "bls_history":     bls_data,
        "kalshi_snapshot": snapshot,
        "metaculus":       {},
        "news":            news_data,
        "divergence_flag": divergence_flag,
        "prompt":          final_prompt
    }

if __name__ == "__main__":
    cfg.TARGET_TICKER = "CPI"
    print("[*] Building Context...")
    result = build_context()
    print("\n[ASSEMBLED PROMPT]\n")
    print(result.get("prompt", "FAILED TO BUILD PROMPT"))
