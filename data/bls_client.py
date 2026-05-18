"""
bls_client.py
Kalshi Agent v2.1 — BLS API Synchronous Poller
Fetches raw government source data for CPI/Jobs (settlement truth).

Rules adhered to:
- Synchronous only (requests library POST)
- 3600s in-memory cache (composite key limits)
- Dynamic year calculation for POST payload
- Filters out suppressed/unreleased "." and "-" values
- Silent failure on network errors (logged via AgentLogger)
- Output shape: [{"period": "2025-M02", "value": "319.1"}, ...] newest first
"""

import time
import requests
import json
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, level, event_type, ticker, msg): 
            print(f"[{level}] {event_type} | {ticker} | {msg}")
    logger = _FallbackLogger()

class BLSClient:
    def __init__(self, ttl_seconds: int = 3600):
        self.base_url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
        self.ttl = ttl_seconds
        self.cache = {}  # Format: {"series_id:limit": (timestamp, data_list)}

    def get_series(self, series_id: str, limit: int = 6) -> list[dict]:
        """
        Fetches the most recent observations from the BLS API.
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
        if not cfg.BLS_API_KEY:
            logger.log_event("WARNING", "BLS_CLIENT", series_id, "BLS_API_KEY is missing. Returning empty history.")
            return []

        # 3. Dynamic Timeline Calculation
        current_year = time.localtime(now).tm_year
        start_year = current_year - 1 # Always pull at least last year to satisfy limit=6

        headers = {'Content-type': 'application/json'}
        payload = json.dumps({
            "seriesid": [series_id],
            "registrationkey": cfg.BLS_API_KEY,
            "startyear": str(start_year),
            "endyear": str(current_year)
        })

        try:
            resp = requests.post(self.base_url, data=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            # BLS returns "REQUEST_SUCCEEDED" or errors in the payload status
            if data.get("status") != "REQUEST_SUCCEEDED":
                logger.log_event("WARNING", "BLS_API_ERROR", series_id, f"API rejected: {data.get('message')}")
                return []

            series_data = data.get("Results", {}).get("series", [])
            if not series_data:
                return []

            observations = series_data[0].get("data", [])
            
            # 4. Transform Output and filter missing/suppressed values
            formatted_data = []
            for obs in observations:
                val = obs.get("value")
                # FIX: Guard against suppressed/unreleased BLS values
                if val and val not in (".", "-"):
                    formatted_data.append({
                        "period": f"{obs.get('year')}-{obs.get('period')}", # e.g., "2025-M02"
                        "value": val
                    })
                
                if len(formatted_data) == limit:
                    break

            # 5. Update Cache and Return
            self.cache[cache_key] = (now, formatted_data)
            logger.log_event("INFO", "BLS_CLIENT", series_id, f"Successfully fetched and cached {len(formatted_data)} records.")
            return formatted_data

        except requests.exceptions.RequestException as e:
            logger.log_event("ERROR", "BLS_API_NETWORK", series_id, str(e))
            return []
        except ValueError as e:
            logger.log_event("ERROR", "BLS_API_JSON", series_id, f"JSON parse failed: {str(e)}")
            return []

# Module-level singleton
bls_client = BLSClient()

if __name__ == "__main__":
    # NOTE: Requires local .venv and .env active. Do NOT run standalone in Docker.
    print("[*] Testing BLS Client...")
    # CUSR0000SA0 is the CPI-U series
    res = bls_client.get_series("CUSR0000SA0", limit=3)
    for r in res:
        print(r)
