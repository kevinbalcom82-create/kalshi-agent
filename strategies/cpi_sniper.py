from strategies.base_strategy import BaseStrategy
from config import cfg
import os

class CPISniper(BaseStrategy):
    @property
    def name(self) -> str:
        return "CPI_SNIPER"

    @property
    def ticker_prefix(self) -> str:
        return cfg.TARGET_TICKER

    def get_prewarm_time(self) -> str:
        return "08:27:00"

    def get_execute_time(self) -> str:
        return "08:30:01"

    def is_active_today(self) -> bool:
        from engine.sniper_scheduler import sniper_scheduler
        
        # 1. Check for a manual override in the .env file
        env_override = os.getenv("CPI_ACTIVE_TODAY")
        if env_override is not None and env_override.strip() != "":
            return env_override.lower() == "true"
            
        # 2. If no override exists, rely completely on the automated calendar
        return sniper_scheduler.is_release_day

    def build_context(self) -> dict:
        from state.context_builder import build_context
        from data.truflation_client import inflation_oracle
        
        ctx = build_context(ticker=self.ticker_prefix)
        
        try:
            oracle_data = inflation_oracle.get_us_inflation()
            yoy_rate = oracle_data.get("yoy_rate")
            source = oracle_data.get("source")
            
            if "prompt" in ctx:
                injection = (
                    f"\n\n[REAL-TIME ORACLE DATA]\n"
                    f"Alternative Inflation Indicator: {yoy_rate}%\n"
                    f"Data Source: {source}\n"
                    f"CRITICAL INSTRUCTION: Factor this real-time Nowcast data heavily into your CPI print prediction."
                )
                ctx["prompt"] += injection
        except Exception as e:
            print(f"Oracle Injection Failed: {e}")
            
        return ctx
