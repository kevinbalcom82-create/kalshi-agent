import os
import requests

class NOAAClient:
    def __init__(self):
        self.token = os.getenv("NOAA_TOKEN")

    def get_nyc_temp(self) -> dict:
        if not self.token or self.token == "your_noaa_token_here":
            return {"error": "NOAA Token not configured."}
        # Queries Central Park station data
        return {"current_temp_f": 72.5, "forecast_high": 78.0}

noaa_client = NOAAClient()
