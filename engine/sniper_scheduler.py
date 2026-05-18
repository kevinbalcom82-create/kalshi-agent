"""
sniper_scheduler.py
Kalshi Agent v2.4 — High-Precision Event Timing
Schedules "Pre-Warm" signals and "Static Strikes" for BLS release days.
"""
import time
from datetime import datetime
from config import cfg
from output.agent_logger import logger

# Official 2026 BLS CPI Release Dates (08:30 AM ET)
CPI_RELEASE_DAYS_2026 = [
    "2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10", 
    "2026-05-12", # Today!
    "2026-06-10", "2026-07-14", "2026-08-12", "2026-09-11", 
    "2026-10-14", "2026-11-10", "2026-12-10"
]

class SniperScheduler:
    def __init__(self):
        self.is_release_day = self._check_if_release_day()
        self.brain_fired_today = False
        self.strike_fired_today = False

    def _check_if_release_day(self) -> bool:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return today_str in CPI_RELEASE_DAYS_2026

    def monitor_clock(self, run_brain_func, execute_trade_func):
        """
        Runs inside the core loop. Checks the time and triggers sniper events.
        """
        if not self.is_release_day:
            return

        now = datetime.now()
        current_time_str = now.strftime("%H:%M:%S")

        # 1. T-180s Pre-Warm (08:27:00 AM)
        # We run the brain early to avoid LLM inference latency during the strike
        if "08:27:00" <= current_time_str <= "08:27:10" and not self.brain_fired_today:
            logger.log_event("INFO", "SNIPER_PREWARM", "MACRO", "T-180s: Pre-warming Brain for CPI drop.")
            run_brain_func(source="SNIPER_PREWARM")
            self.brain_fired_today = True

        # 2. Static Strike (08:30:01 AM)
        # The moment the data drops, we fire the cached signal
        if "08:30:01" <= current_time_str <= "08:30:10" and not self.strike_fired_today:
            logger.log_event("INFO", "SNIPER_STRIKE", "MACRO", "08:30:01: Executing Sniper Strike.")
            execute_trade_func(source="SNIPER_STRIKE")
            self.strike_fired_today = True

    def reset_daily(self):
        """Reset flags at midnight."""
        self.brain_fired_today = False
        self.strike_fired_today = False
        self.is_release_day = self._check_if_release_day()

sniper_scheduler = SniperScheduler()
