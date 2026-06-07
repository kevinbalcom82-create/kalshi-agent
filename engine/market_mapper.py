"""
market_mapper.py
Kalshi Agent v3.0 — Polymarket Twin Finder
Given a Kalshi ticker (e.g. KXCPI), finds the matching Polymarket market
so the arbitrage engine knows which two markets to trade simultaneously.
Uses manual overrides first, fuzzy string matching as fallback.
"""
import re
import requests
from difflib import SequenceMatcher
from typing import Optional

# Manual overrides: Kalshi series prefix → Polymarket event slug
# Add new markets here as you expand to new event types
MANUAL_OVERRIDES = {
    "CPICORE":   "us-core-cpi",
    "CPIM":      "us-cpi-monthly",
    "KXCPI":     "us-cpi",
    "KXFED":     "fed-rate-decision",
    "KXNFP":     "nonfarm-payrolls",
    "KXGDP":     "us-gdp",
    "KXNBA":     None,   # Sports — no Polymarket twin
    "KXINTRADAY": None,  # Equities intraday — no Polymarket twin
}

POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"


def _similarity_score(a: str, b: str) -> float:
    """Fuzzy string similarity — 0.0 to 1.0."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _normalize_question(text: str) -> str:
    """Strips punctuation and normalizes whitespace for comparison."""
    text = re.sub(r'[^\w\s.]', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()


def resolve_polymarket_twin(
    kalshi_ticker: str,
    kalshi_question: Optional[str] = None
) -> Optional[dict]:
    """
    Looks up the Polymarket market that corresponds to a Kalshi ticker.

    Returns dict with:
        condition_id   — Polymarket condition ID for order routing
        slug           — Human-readable event slug
        token_ids      — List of token IDs for WebSocket subscription
        similarity_pct — Match confidence (100 = exact manual override)

    Returns None if no match found or market type has no Polymarket twin.
    """
    # Strip date suffix to get series prefix (e.g. KXCPI-26MAY → KXCPI)
    series = re.split(r'-\d', kalshi_ticker)[0].upper()

    if series in MANUAL_OVERRIDES:
        slug = MANUAL_OVERRIDES[series]
        if not slug:
            return None  # Known market type with no Polymarket equivalent

        try:
            resp = requests.get(
                f"{POLYMARKET_GAMMA_API}/events",
                params={"slug": slug, "active": "true"},
                timeout=5
            )
            if resp.status_code == 200 and resp.json():
                markets = resp.json()[0].get("markets", [])
                if markets:
                    return {
                        "condition_id":   markets[0].get("conditionId"),
                        "slug":           slug,
                        "token_ids":      [
                            t["token_id"]
                            for t in markets[0].get("tokens", [])
                            if t.get("token_id")
                        ],
                        "similarity_pct": 100.0
                    }
        except Exception:
            pass

    return None
