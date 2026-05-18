import time
import yfinance as yf
from decimal import Decimal, InvalidOperation
from config import cfg

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

CACHE_TTL = 60

class YFinanceClient:
    def __init__(self):
        self._cache = {}

    def _to_dec(self, val) -> Decimal:
        try:
            return Decimal(str(round(float(val), 4)))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    def get_snapshot(self, symbol: str) -> dict:
        now = time.time()
        if symbol in self._cache:
            cached_time, cached_data = self._cache[symbol]
            if now - cached_time < CACHE_TTL:
                return cached_data

        try:
            ticker = yf.Ticker(symbol)
            info   = ticker.fast_info 

            result = {
                "symbol":        symbol,
                "price":         str(self._to_dec(info.last_price)),
                "day_high":      str(self._to_dec(info.day_high)),
                "day_low":       str(self._to_dec(info.day_low)),
                "prev_close":    str(self._to_dec(info.previous_close)),
                "volume":        str(int(info.last_volume or 0)),
                "market_cap":    str(self._to_dec(getattr(info, "market_cap", 0))),
                "timestamp":     int(now),
            }

            try:
                price    = self._to_dec(info.last_price)
                prev     = self._to_dec(info.previous_close)
                if prev > Decimal("0"):
                    pct_change = ((price - prev) / prev) * Decimal("100")
                    result["pct_change"] = str(round(pct_change, 4))
                else:
                    result["pct_change"] = "0"
            except (InvalidOperation, TypeError):
                result["pct_change"] = "0"

            self._cache[symbol] = (now, result)
            logger.log_event("INFO", "YFINANCE_OK", symbol, f"Price: {result['price']} | Change: {result['pct_change']}%")
            return result
        except Exception as e:
            logger.log_event("ERROR", "YFINANCE_FAIL", symbol, str(e))
            return {}

    def get_market_context(self) -> dict:
        spx = self.get_snapshot("^GSPC")
        vix = self.get_snapshot("^VIX")
        if not spx or not vix:
            logger.log_event("WARNING", "YFINANCE_INCOMPLETE", "EQUITIES", f"SPX: {'OK' if spx else 'FAIL'} | VIX: {'OK' if vix else 'FAIL'}")
        return {"spx": spx, "vix": vix, "data_quality": "FULL" if (spx and vix) else "PARTIAL"}

yfinance_client = YFinanceClient()
