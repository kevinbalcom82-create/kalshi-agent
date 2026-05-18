"""
fed_client.py
Kalshi Agent v2.5 — Phase 3: FOMC Fed Watcher Data Client
Fetches 2Y Yields, Fed Funds Rates, and scrapes the FOMC Press Release RSS.
"""

import time
import datetime
import requests
import xml.etree.ElementTree as ET
from config import cfg
from output.agent_logger import logger
from data.fred_client import fred_client

class FedClient:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 3600  # 1 hour TTL

        self.FOMC_DATES = [
            # 2026
            "2026-01-29", "2026-03-19", "2026-05-08",
            "2026-06-18", "2026-07-30", "2026-09-17",
            "2026-11-05", "2026-12-17",
            # 2027 (preliminary)
            "2027-01-28", "2027-03-18", "2027-05-06",
            "2027-06-17", "2027-07-29", "2027-09-16",
            "2027-11-04", "2027-12-16"
        ]

        self.HAWKISH_PHRASES = [
            "higher for longer", "remain restrictive",
            "not yet confident", "inflation remains elevated",
            "further firming", "additional policy firming",
            "persistent inflation", "upside risks to inflation"
        ]
        self.DOVISH_PHRASES = [
            "inflation has eased", "labor market has cooled",
            "appropriate to reduce", "balance of risks",
            "gained greater confidence", "moving toward",
            "easing of inflation pressures", "downside risks"
        ]

    def _get_date_info(self):
        today_date = datetime.date.today()
        today_str = today_date.strftime("%Y-%m-%d")
        
        is_fomc_today = today_str in self.FOMC_DATES
        
        next_date_str = None
        days_to = -1
        
        for f_date in self.FOMC_DATES:
            fd = datetime.datetime.strptime(f_date, "%Y-%m-%d").date()
            if fd >= today_date:
                next_date_str = f_date
                days_to = (fd - today_date).days
                break
                
        return is_fomc_today, next_date_str, days_to

    def get_fed_context(self) -> dict:
        now = time.time()
        if "context" in self._cache and now - self._cache["context"]["timestamp"] < self._cache_ttl:
            return self._cache["context"]["data"]

        is_fomc_today, next_fomc_date, days_to_fomc = self._get_date_info()

        context = {
            "is_fomc_today": is_fomc_today,
            "next_fomc_date": next_fomc_date,
            "days_to_fomc": days_to_fomc,
            "two_year_yield": "0.0",
            "yield_5d_change": "0.0",
            "yield_trend_5d": "0.0",
            "yield_since_last_fomc": "0.0",
            "yield_trend": "FLAT",
            "fed_funds_rate": "0.0",
            "rate_change_expected": False,
            "press_release_title": "Unavailable",
            "press_release_date": "Unavailable",
            "press_release_url": "Unavailable",
            "tone_score": 0,
            "tone_label": "NEUTRAL",
            "data_quality": "FULL"
        }

        try:
            dgs2_data = fred_client.get_series("DGS2", limit=30)
            if dgs2_data and len(dgs2_data) >= 5:
                valid_yields = [d for d in dgs2_data if str(d.get("value", ".")) != '.']
                
                if len(valid_yields) >= 5:
                    latest_val = cfg.to_decimal(valid_yields[0]["value"])
                    old_5d_val = cfg.to_decimal(valid_yields[4]["value"])
                    
                    change_5d = latest_val - old_5d_val
                    context["two_year_yield"] = str(latest_val)
                    context["yield_5d_change"] = f"{change_5d:+.2f}"
                    context["yield_trend_5d"] = f"{change_5d:+.2f}"
                    
                    if change_5d > cfg.to_decimal("0.05"):
                        context["yield_trend"] = "RISING"
                    elif change_5d < cfg.to_decimal("-0.05"):
                        context["yield_trend"] = "FALLING"
                    else:
                        context["yield_trend"] = "FLAT"

                    if len(valid_yields) >= 20:
                        oldest_val = cfg.to_decimal(valid_yields[-1]["value"])
                        change_since_last = latest_val - oldest_val
                        context["yield_since_last_fomc"] = f"{change_since_last:+.2f}"
                else:
                    context["data_quality"] = "PARTIAL"
            else:
                context["data_quality"] = "PARTIAL"

            dfed_data = fred_client.get_series("DFEDTARU", limit=2)
            if dfed_data and len(dfed_data) > 0:
                val = str(dfed_data[0].get("value", "0.0"))
                if val != '.':
                    context["fed_funds_rate"] = val

            rss_url = "https://www.federalreserve.gov/feeds/press_all.xml"
            resp = requests.get(rss_url, timeout=10)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                found_item = None
                
                for item in root.findall(".//item"):
                    title = item.find("title").text or ""
                    desc = item.find("description").text or ""
                    if "Federal Open Market Committee" in title or "FOMC" in title or "Federal Open Market Committee" in desc:
                        found_item = item
                        break
                
                if found_item is not None:
                    context["press_release_title"] = found_item.find("title").text
                    context["press_release_url"] = found_item.find("link").text
                    context["press_release_date"] = found_item.find("pubDate").text
                    
                    text_to_score = f"{context['press_release_title']} {found_item.find('description').text or ''}".lower()
                    score = 0
                    
                    for hw in self.HAWKISH_PHRASES:
                        score -= text_to_score.count(hw)
                    for dw in self.DOVISH_PHRASES:
                        score += text_to_score.count(dw)
                        
                    context["tone_score"] = score
                    if score <= -1:
                        context["tone_label"] = "HAWKISH"
                    elif score >= 1:
                        context["tone_label"] = "DOVISH"
                    else:
                        context["tone_label"] = "NEUTRAL"
            else:
                context["data_quality"] = "PARTIAL"

        except Exception as e:
            logger.log_event("ERROR", "FED_CLIENT_FAIL", "SYSTEM", str(e))
            context["data_quality"] = "UNAVAILABLE"

        if context["yield_trend"] in ["RISING", "FALLING"]:
            context["rate_change_expected"] = True

        self._cache["context"] = {
            "timestamp": now,
            "data": context
        }
        
        return context

fed_client = FedClient()
