import requests
from decimal import Decimal
from config import cfg

print("[*] Scouting KXNASDAQ100 for the 'Coin-Flip' strikes...")

url = f"{cfg.REST_BASE_URL}/trade-api/v2/markets?series_ticker=KXNASDAQ100&status=open"
res = requests.get(url, headers={"Accept": "application/json"})
markets = res.json().get('markets', [])

found_count = 0
for m in markets:
    ticker = m['ticker']
    m_url = f"{cfg.REST_BASE_URL}/trade-api/v2/markets/{ticker}"
    m_res = requests.get(m_url, headers={"Accept": "application/json"}).json()
    market_info = m_res.get('market', {})
    
    ask_str = market_info.get('yes_ask_dollars')
    ask = Decimal(ask_str) if ask_str else Decimal("0.00")
    
    if ask > 0:
        # Highlight markets near $0.50
        status = "🎯 SWEET SPOT" if 0.30 <= ask <= 0.70 else "➖ OUTSIDE"
        print(f"{status}: {ticker} | Price: ${ask}")
        found_count += 1

if found_count == 0:
    print("❌ No liquid markets found. Kalshi might be between sessions.")
