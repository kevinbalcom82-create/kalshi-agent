"""
news_client.py
Kalshi Agent v2.3 — News Sentiment
GDELT disabled — timing out. Returns empty sentiment silently.
Re-enable when alternative news source is wired.
"""

from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

EMPTY = {"headlines": [], "sentiment_score": 0.0, "gdelt_tone": 0.0}

class NewsClient:
    def __init__(self):
        self.cache = {}

    def get_sentiment(self, ticker: str) -> dict:
        """GDELT disabled — returns empty sentiment silently."""
        return EMPTY

news_client = NewsClient()
