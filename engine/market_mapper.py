import re, requests
from difflib import SequenceMatcher
from typing import Optional

MANUAL_OVERRIDES = {"CPICORE": "us-core-cpi", "CPIM": "us-cpi-monthly", "KXCPI": "us-cpi", "KXFED": "fed-rate-decision", "KXNFP": "nonfarm-payrolls", "KXGDP": "us-gdp", "KXNBA": None, "KXINTRADAY": None}
POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"

def _similarity_score(a: str, b: str) -> float: return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _normalize_question(text: str) -> str:
    text = re.sub(r'[^\w\s.]', ' ', text.lower())
    return re.sub(r'\s+', ' ', text).strip()

def resolve_polymarket_twin(kalshi_ticker: str, kalshi_question: Optional[str] = None) -> Optional[dict]:
    series = re.split(r'-\d', kalshi_ticker)[0].upper()
    if series in MANUAL_OVERRIDES:
        slug = MANUAL_OVERRIDES[series]
        if not slug:
            return None
        try:
            resp = requests.get(f"{POLYMARKET_GAMMA_API}/events", params={"slug": slug, "active": "true"}, timeout=5)
            if resp.status_code == 200 and resp.json():
                markets = resp.json()[0].get("markets", [])
                if markets: return {"condition_id": markets[0].get("conditionId"), "slug": slug, "token_ids": [t["token_id"] for t in markets[0].get("tokens", []) if t.get("token_id")], "similarity_pct": 100.0}
        except Exception: pass
    return None
