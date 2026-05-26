from strategies.base_strategy import BaseStrategy
import datetime

class NFPSniper(BaseStrategy):
    @property
    def name(self) -> str:
        return "NFP_SNIPER"

    @property
    def ticker_prefix(self) -> str:
        return "KXNFP" 

    def get_prewarm_time(self) -> str:
        return "08:27:00"

    def get_execute_time(self) -> str:
        return "08:30:01"

    def is_active_today(self) -> bool:
        today = datetime.date.today()
        return today.weekday() == 4 and 1 <= today.day <= 7

    def build_context(self) -> dict:
        from state.context_builder import build_context
        
        ctx = build_context(ticker=self.ticker_prefix)
        ctx["strategy_name"] = self.name
        
        return ctx
