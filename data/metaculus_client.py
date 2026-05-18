"""
metaculus_client.py
Kalshi Agent v2.3 — Metaculus Crowd Forecast
Disabled — API returning 403. Returns empty forecast silently.
"""

EMPTY = {"questions": [], "avg_probability": None}

class MetaculusClient:
    def __init__(self):
        self.cache = {}

    def get_forecast(self, ticker: str) -> dict:
        """Metaculus disabled — returns empty forecast silently."""
        return EMPTY

metaculus_client = MetaculusClient()
