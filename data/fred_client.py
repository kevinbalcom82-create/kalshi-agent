"""
fred_client.py
Kalshi Agent v2.1 — FRED API Synchronous Poller
Fetches macroeconomic historical actuals (e.g., CPIAUCSL) for Gemini baseline.

Rules adhered to:
- Synchronous only (requests library)
- 3600s in-memory cache (composite key limits)
- Filters out missing/unreleased "." values
- Silent failure on network errors (logged via AgentLogger)
- Returns string values (caller converts via cfg.to_decimal())
- Output shape: [{"date": "YYYY-MM-DD", "value": "123.45"}, ...] newest first
"""

import time
import requests
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, level, event_type, ticker, msg): 
            print(f"[{level}] {event_type} | {ticker} | {msg}")
    logger = _FallbackLogger()

class FredClient:
    def __init__(self, ttl_seconds: int = 3600):
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"
        self.ttl = ttl_seconds
        self.cache = {}  # Format: {"series_id:limit": (timestamp, data_list)}

    def get_series(self, series_id: str, limit: int = 6) -> list[dict]:
        """
        Fetches the most recent observations for a FRED series.
        Returns a list of dicts newest-first, using cached data if within TTL.
        """
        now = time.time()
        cache_key = f"{series_id}:{limit}"
        
        # 1. Check in-memory cache
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if now - cached_time < self.ttl:
                return cached_data

        # 2. Config Validation
        if not cfg.FRED_API_KEY:
            logger.log_event("WARNING", "FRED_CLIENT", series_id, "FRED_API_KEY is missing. Returning empty history.")
            return []

        # 3. Network Request
        # Request double the limit to ensure enough valid data after filtering out "."
        params = {
            "series_id": series_id,
            "api_key": cfg.FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit * 2 
        }

        try:
            resp = requests.get(self.base_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            observations = data.get("observations", [])
            
            # 4. Transform and Filter missing "." values
            formatted_data = []
            for obs in observations:
                val = obs.get("value")
                if val and val != ".":
                    formatted_data.append({
                        "date": obs.get("date"),
                        "value": val
                    })
                
                if len(formatted_data) == limit:
                    break

            # 5. Update Cache and Return
            self.cache[cache_key] = (now, formatted_data)
            logger.log_event("INFO", "FRED_CLIENT", series_id, f"Successfully fetched and cached {len(formatted_data)} records.")
            return formatted_data

        except requests.exceptions.RequestException as e:
            logger.log_event("ERROR", "FRED_API_NETWORK", series_id, str(e))
            return []
        except ValueError as e:
            logger.log_event("ERROR", "FRED_API_JSON", series_id, f"JSON parse failed: {str(e)}")
            return []

# Module-level singleton
fred_client = FredClient()

if __name__ == "__main__":
    # NOTE: This manual test block requires the local .venv and .env to be active.
    # Do NOT run this directly inside the Docker container without the SSD volume mounted
    # or the AgentLogger initialization may fail/corrupt.
    print("[*] Testing FRED Client...")
    res = fred_client.get_series("CPIAUCSL", limit=3)
    for r in res:
        print(r)
