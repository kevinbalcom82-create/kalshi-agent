"""
rss_client.py
Kalshi Agent v2.4 — Free RSS Sentiment Engine
Replaces GDELT with standard RSS feeds. Pure Python, no new dependencies.
"""

import requests
import xml.etree.ElementTree as ET
import time
from output.agent_logger import logger

FEEDS = {
    "CPI": [
        "https://www.reutersagency.com/feed/?best-topics=business&post_type=best",
        "https://feeds.a.dj.com/rss/WSJEconomy.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml"
    ],
    "FED": [
        "https://www.federalreserve.gov/feeds/press_all.xml"
    ]
}

BULL_KEYS = ["surges", "rises", "hot", "above", "beats", "growth", "high", "spike"]
BEAR_KEYS = ["falls", "cools", "below", "misses", "drops", "easing", "low", "slows"]

class RSSClient:
    def __init__(self):
        self._cache = {}
        self._ttl = 1800  # 30 min cache

    def get_sentiment(self, category: str) -> dict:
        now = time.time()
        category = category.upper()
        
        if category in self._cache:
            data, expiry = self._cache[category]
            if now < expiry: return data

        urls = FEEDS.get(category, FEEDS["CPI"])
        headlines = []
        
        for url in urls:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall(".//item"):
                        title = item.find("title")
                        if title is not None and title.text:
                            headlines.append(title.text)
            except Exception as e:
                continue

        score = 0.0
        if headlines:
            text = " ".join(headlines).lower()
            bull = sum(text.count(w) for w in BULL_KEYS)
            bear = sum(text.count(w) for w in BEAR_KEYS)
            if (bull + bear) > 0:
                score = (bull - bear) / (bull + bear)
        
        result = {
            "headlines": headlines[:10],
            "sentiment_score": round(score, 2),
            "gdelt_tone": 0.0
        }
        self._cache[category] = (result, now + self._ttl)
        return result

rss_client = RSSClient()
