"""
core_engine.py
Kalshi Agent v2.0 — Orchestration Entry Point
Currently routing to PolymarketStream (Kalshi unfunded)
Swap back to KalshiStream by changing the import below.
"""

import sys
import signal
from config import cfg
from output.agent_logger import logger
from state.market_state import state_manager

# ── Stream Selection ──────────────────────────────────────────────────────────
# Swap this import when Kalshi account is funded:
# from data.kalshi_stream import KalshiStream as Stream
from data.polymarket_stream import PolymarketStream as Stream


def validate_config():
    missing = []
    if missing:
        print(f"[FATAL] Missing required keys: {', '.join(missing)}")
        print("[FATAL] Fill in your .env file before starting.")
        sys.exit(1)
    print(f"[OK] Config validated | DB: {cfg.DB_PATH}")


def shutdown_handler(signum, frame):
    print(f"\n[SHUTDOWN] Signal {signum} — flushing database...")
    logger.log_event("INFO", "SHUTDOWN", None, f"Signal {signum} — clean shutdown.")
    getattr(logger, "close", lambda: None)()
    print("[SHUTDOWN] Clean exit.")
    sys.exit(0)


def main():
    print("=" * 52)
    print("  Kalshi AI Agent System v2.0")
    print("  Suncoast Agent Factory")
    print("  Feed: Polymarket CLOB (public)")
    print("=" * 52)

    print("\n[BOOT] 1/3 — Validating config...")
    validate_config()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT,  shutdown_handler)

    print("[BOOT] 2/3 — Persistence layer active.")
    print(f"       Heartbeat: every {cfg.HEARTBEAT_INTERVAL_SECONDS // 60} min")
    print("[BOOT] 3/3 — State manager ready.")

    print("\n[BOOT] Starting stream and market discovery...")
    stream = Stream()

    try:
        stream.connect()
    except Exception as e:
        logger.log_event("CRITICAL", "FATAL", None, str(e))
        print(f"\n[FATAL] {e}")
    finally:
        stream.stop()
        getattr(logger, "close", lambda: None)()
        sys.exit(0)


if __name__ == "__main__":
    main()
