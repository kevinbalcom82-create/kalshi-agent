from abc import ABC, abstractmethod
from decimal import Decimal
import threading

class BaseStrategy(ABC):
    def __init__(self):
        self._cached_signal = None
        self._signal_lock = threading.Lock()

    @property
    @abstractmethod
    def name(self) -> str: pass

    @property
    @abstractmethod
    def ticker_prefix(self) -> str: pass

    @abstractmethod
    def get_prewarm_time(self) -> str: pass

    @abstractmethod
    def get_execute_time(self) -> str: pass

    @abstractmethod
    def is_active_today(self) -> bool: pass

    @abstractmethod
    def build_context(self) -> dict: pass

    def pre_warm(self):
        from engine.brain import generate_signal
        from engine.cro_auditor import audit_signal
        from output.agent_logger import logger
        from output.telegram_notifier import send_telegram

        if not self.is_active_today():
            return

        try:
            context = self.build_context()
            raw = generate_signal(context)
            audited = audit_signal(raw, context) 

            if audited.get("veto"):
                logger.log_event("WARNING", "CRO_VETO", self.name, audited.get("audit_notes", "Vetoed"))
                return

            with self._signal_lock:
                self._cached_signal = audited

            logger.log_event("INFO", "PRE_WARM_OK", self.name, f"Signal cached: {audited.get('direction')} @ {audited.get('confidence')}%")
        except Exception as e:
            logger.log_event("CRITICAL", "PRE_WARM_CRASH", self.name, str(e))
            send_telegram(f"🚨 {self.name} PRE_WARM CRASHED: {e}")

    def execute(self, execution_lock: threading.Lock, reserve_fn, release_fn):
        from engine.kelly_sizer import calculate_kelly
        from engine.kalshi_router import execute_trade
        from data.kalshi_market import get_market_price
        from output.agent_logger import logger
        from output.telegram_notifier import send_telegram
        from config import cfg

        with self._signal_lock:
            signal = self._cached_signal
            self._cached_signal = None

        if not signal:
            return

        if not execution_lock.acquire(blocking=False):
            logger.log_event("WARNING", "EXEC_BLOCKED", self.name, "Execution lock held by another strategy.")
            return

        try:
            fresh_price = Decimal(str(get_market_price(self.ticker_prefix)))
            cached_price = Decimal(str(signal.get("suggested_entry_dollars", "0")))
            drift = abs(fresh_price - cached_price)

            if drift > Decimal("0.05"):
                msg = f"Price drifted {drift} — aborting {self.name}"
                logger.log_event("WARNING", "PRICE_DRIFT", self.name, msg)
                send_telegram(f"⚠️ {msg}")
                return

            kelly = calculate_kelly(Decimal(str(cfg.BANKROLL)), Decimal(str(signal["confidence"])), fresh_price)

            if kelly.get("contracts", 0) == 0 or kelly.get("veto"):
                logger.log_event("INFO", "NO_EDGE", self.name, "Kelly returned 0 contracts.")
                return

            position = Decimal(str(kelly.get("position_dollars", "0")))
            if not reserve_fn(position):
                logger.log_event("WARNING", "CAPITAL_CAP", self.name, "Allocation cap reached — skipped.")
                return

            kelly["side"] = signal["direction"]

            try:
                result = execute_trade(kelly, self.ticker_prefix)
                logger.log_event("INFO", "ORDER_SENT", self.name, f"order_id={result.get('order_id')} status={result.get('status')}")
                send_telegram(f"✅ *{self.name} STRIKE*\nSide: {kelly['side']}\nContracts: {kelly['contracts']}\nEntry: ${fresh_price}")
            except Exception as e:
                release_fn(position)
                logger.log_event("CRITICAL", "ORDER_FAIL", self.name, str(e))
                send_telegram(f"🚨 {self.name} ORDER FAILED: {e}\nCHECK KALSHI MANUALLY")
        finally:
            execution_lock.release()
