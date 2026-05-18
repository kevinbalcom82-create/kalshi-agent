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
        return os.getenv("CPI_ACTIVE_TODAY", "false").lower() == "true"

    def build_context(self) -> dict:
        from state.context_builder import build_context
        return build_context(ticker=self.ticker_prefix)
