"""
arb_scanner.py
Kalshi Agent v3.0 — Cross-Exchange Arbitrage Opportunity Scanner
Runs as a daemon thread, wakes every 30 seconds, and checks whether
the YES price spread between Kalshi and Polymarket is wide enough
to capture after fees (minimum 6 cent gross spread).

When a profitable spread is found it sizes the position at 10% of
bankroll (capped at 50 contracts) and fires unified_router.execute_arbitrage().

Wired into core_engine.py via start_arb_scanner().
"""
import time
import threading
import requests
from decimal import Decimal
from typing import Callable

from config import cfg
from engine.kalshi_ticker_resolver import resolve_kalshi_ticker
from engine.market_mapper import resolve_polymarket_twin
from engine.unified_router import calculate_arb_spread, execute_arbitrage

try:
    from output.agent_logger import logger
except ImportError:
    class _FallbackLogger:
        def log_event(self, l, e, t, m): print(f"[{l}] {e} | {t} | {m}")
    logger = _FallbackLogger()

try:
    from output.telegram_notifier import send_telegram
except ImportError:
    def send_telegram(msg): print(f"[TELEGRAM STUB] {msg}")

SCAN_INTERVAL_SECONDS = 30
MIN_CONTRACTS         = 5
MAX_CONTRACTS         = 50


def _fetch_polymarket_bid(token_id: str) -> Decimal:
    """Fetches the best (highest) bid price from Polymarket CLOB REST API."""
    try:
        resp = requests.get(
            "https://clob.polymarket.com/book",
            params  = {"token_id": token_id},
            timeout = 5
        )
        if resp.status_code != 200:
            return Decimal("0")

        bids = resp.json().get("bids", [])
        if not bids:
            return Decimal("0")

        best_bid = max(bids, key=lambda x: float(x.get("price", 0)))
        return Decimal(str(best_bid.get("price", "0")))

    except Exception:
        return Decimal("0")


def _log_spread_safely(
    exact_ticker: str,
    poly_token:   str,
    kalshi_ask:   Decimal,
    poly_bid:     Decimal,
    gross_spread: Decimal,
    net_spread:   Decimal,
    is_profitable: bool,
    executed:     bool
) -> None:
    """
    Logs spread data to agent_logger if log_arb_spread exists,
    falls back to log_event gracefully if it doesn't.
    """
    try:
        from output.agent_logger import logger as agent_logger
        if hasattr(agent_logger, "log_arb_spread"):
            agent_logger.log_arb_spread(
                exact_ticker, poly_token,
                kalshi_ask, poly_bid,
                gross_spread, net_spread,
                is_profitable, executed
            )
        else:
            # Fallback — log as a standard event so nothing is lost
            agent_logger.log_event(
                "INFO", "ARB_SPREAD", exact_ticker,
                f"Kalshi: ${kalshi_ask} | Poly: ${poly_bid} | "
                f"Gross: ${gross_spread} | Net: ${net_spread} | "
                f"Profitable: {is_profitable} | Executed: {executed}"
            )
    except Exception:
        pass


def _scan_once(
    strategy_tickers: list[str],
    reserve_fn:       Callable,
    release_fn:       Callable
) -> None:
    """
    Single scan pass across all active strategy tickers.
    Called every SCAN_INTERVAL_SECONDS by the daemon thread.
    """
    for series_prefix in strategy_tickers:
        try:
            # 1. Resolve exact Kalshi ticker and live ask price
            exact_ticker, kalshi_ask = resolve_kalshi_ticker(series_prefix)
            if kalshi_ask <= Decimal("0"):
                continue

            # 2. Find matching Polymarket market
            twin = resolve_polymarket_twin(exact_ticker)
            if not twin or not twin.get("token_ids"):
                continue
            poly_token = twin["token_ids"][0]

            # 3. Fetch Polymarket best bid
            poly_bid = _fetch_polymarket_bid(poly_token)
            if poly_bid <= Decimal("0"):
                continue

            # 4. Calculate spread profitability
            spread_data  = calculate_arb_spread(kalshi_ask, poly_bid, MIN_CONTRACTS)
            gross_spread = Decimal(spread_data["gross_spread"])
            net_spread   = Decimal(spread_data["net_spread"])
            is_profitable = spread_data["is_profitable"]

            # Log every scan result for dashboard visibility
            _log_spread_safely(
                exact_ticker, poly_token,
                kalshi_ask, poly_bid,
                gross_spread, net_spread,
                is_profitable, False
            )

            if not is_profitable:
                continue

            # 5. Profitable spread found — size and execute
            logger.log_event(
                "INFO", "ARB_EDGE_FOUND", exact_ticker,
                f"Gross: ${gross_spread} | Net: ${net_spread}"
            )
            send_telegram(
                f"⚡ *ARB EDGE FOUND*\n"
                f"Ticker: `{exact_ticker}`\n"
                f"Kalshi Ask: ${kalshi_ask} | Poly Bid: ${poly_bid}\n"
                f"Gross Spread: ${gross_spread} | Net: ${net_spread}"
            )

            # Size at 10% bankroll, capped at MAX_CONTRACTS
            contracts = max(
                MIN_CONTRACTS,
                min(
                    int(Decimal(str(cfg.BANKROLL)) * Decimal("0.10") / kalshi_ask),
                    MAX_CONTRACTS
                )
            )
            capital_needed = kalshi_ask * contracts

            if not reserve_fn(capital_needed):
                logger.log_event(
                    "WARNING", "ARB_CAP_BLOCKED", exact_ticker,
                    "Capital reserve limit reached — skipping."
                )
                continue

            try:
                result = execute_arbitrage(
                    exact_ticker, contracts, kalshi_ask,
                    poly_token,   contracts, poly_bid
                )

                if result.get("success", False):
                    _log_spread_safely(
                        exact_ticker, poly_token,
                        kalshi_ask, poly_bid,
                        gross_spread, net_spread,
                        True, True
                    )
                    send_telegram(
                        f"✅ *ARB EXECUTED*\n"
                        f"Ticker: `{exact_ticker}`\n"
                        f"Contracts: {contracts} | "
                        f"Expected profit: ${spread_data['expected_profit_dollars']}"
                    )

                # Release capital if leg risk triggered
                # (unified_router handles orphan closure separately)
                if result.get("leg_risk_triggered"):
                    release_fn(capital_needed)

            except Exception as e:
                release_fn(capital_needed)
                logger.log_event("ERROR", "ARB_EXECUTE_FAIL", exact_ticker, str(e))

        except Exception:
            continue


def start_arb_scanner(
    strategy_tickers: list[str],
    reserve_fn:       Callable,
    release_fn:       Callable
) -> threading.Thread:
    """
    Starts the arbitrage scanner as a daemon thread.
    Call this from core_engine.py after strategies are registered.

    strategy_tickers: list of series prefixes to monitor
                      e.g. ["KXCPI", "KXNFP", "KXFED"]
    reserve_fn:       core_engine.reserve_capital
    release_fn:       core_engine.release_capital
    """
    def _loop():
        time.sleep(15)  # Brief startup delay to let streams initialize
        while True:
            try:
                _scan_once(strategy_tickers, reserve_fn, release_fn)
            except Exception:
                pass
            time.sleep(SCAN_INTERVAL_SECONDS)

    t = threading.Thread(target=_loop, daemon=True, name="ArbScanner")
    t.start()
    logger.log_event("INFO", "ARB_SCANNER_START", "SYSTEM",
                     f"Arb scanner active — monitoring {strategy_tickers}")
    return t
