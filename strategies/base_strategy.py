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
        from engine.kalshi_ticker_resolver import resolve_kalshi_ticker, invalidate_cache
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
            exact_ticker, fresh_price = resolve_kalshi_ticker(self.ticker_prefix)
            cached_price_raw = signal.get("suggested_entry_dollars")
            
            # THE DRIFT FIX: If AI gives no price, use the fresh market price
            if not cached_price_raw or str(cached_price_raw) in ("0", "0.0", ""):
                cached_price = fresh_price
            else:
                cached_price = Decimal(str(cached_price_raw))
                
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

            position = Decimal(str(kelly.get("capital_at_risk", kelly.get("position_dollars", "0"))))
            if not reserve_fn(position):
                logger.log_event("WARNING", "CAPITAL_CAP", self.name, "Allocation cap reached — skipped.")
                return

            kelly["side"] = signal["direction"]

            try:
                import os
                from dotenv import load_dotenv
                load_dotenv()
                if os.getenv('EXECUTION_MODE', 'LIVE').upper() == 'PAPER':
                    from engine.ghost_book import execute_paper_trade
                    reasoning = signal.get('audit_notes', signal.get('reasoning', 'Paper trade simulated.'))
                    edge = signal.get('edge_source', 'UNKNOWN')
                    success = execute_paper_trade(self.name, exact_ticker, kelly['side'], signal['confidence'], float(fresh_price), kelly['contracts'], edge, reasoning)
                    if success:
                        logger.log_event('INFO', 'PAPER_ORDER_SENT', self.name, f'Simulated {kelly["contracts"]} contracts.')
                        send_telegram(f'👻 *{self.name} PAPER STRIKE*\nSide: {kelly["side"]}\nContracts: {kelly["contracts"]}\nEntry: ${fresh_price}')
                    else:
                        release_fn(position)
                else:
                    result = execute_trade(kelly, exact_ticker)
                    invalidate_cache(self.ticker_prefix)
                    logger.log_event("INFO", "ORDER_SENT", self.name, f"order_id={result.get('order_id')} status={result.get('status')}")
                    send_telegram(f"✅ *{self.name} STRIKE*\nSide: {kelly['side']}\nContracts: {kelly['contracts']}\nEntry: ${fresh_price}")
            except Exception as e:
                release_fn(position)
                logger.log_event("CRITICAL", "ORDER_FAIL", self.name, str(e))
                send_telegram(f"🚨 {self.name} ORDER FAILED: {e}\nCHECK KALSHI MANUALLY")
        finally:
            execution_lock.release()
