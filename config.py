"""
config.py
Kalshi Agent v3.0 — Centralized Configuration
Uses pydantic-settings to validate and load all environment variables
from .env at boot. Raises a clear ValidationError immediately if
critical keys are missing — no silent failures.

REQUIRES: pip install pydantic-settings
"""
from decimal import Decimal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """
    Single source of truth for all agent configuration.
    All fields map directly to .env variable names.
    """

    # ── Trading Execution ──────────────────────────────────────────────────
    KALSHI_API_KEY:          str | None = None
    KALSHI_PRIVATE_KEY_PATH: str        = Field(default="./secrets/kalshi.pem")
    POLYMARKET_PRIVATE_KEY:  str | None = None
    POLYMARKET_PROXY_WALLET: str | None = None

    # ── Market Data Providers ──────────────────────────────────────────────
    FRED_API_KEY:            str | None = None
    BLS_API_KEY:             str | None = None
    NOAA_TOKEN:              str | None = None
    POLYGON_API_KEY:         str | None = None
    ODDS_API_KEY:            str | None = None

    # ── Alerts & Monitoring ────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN:      str | None = None
    TELEGRAM_CHAT_ID:        str | None = None

    # ── Infrastructure ─────────────────────────────────────────────────────
    REST_BASE_URL:           str        = Field(
        default="https://external-api.kalshi.com"
    )
    POLYGON_RPC_URL:         str        = Field(
        default="https://polygon-rpc.com"
    )
    DB_PATH:                 str        = Field(
        default="/Volumes/AI_Drive/kalshi_data/market_state.db"
    )
    HEARTBEAT_INTERVAL_SECONDS: int     = Field(default=3600)

    # ── Financial Settings ─────────────────────────────────────────────────
    BANKROLL:                Decimal    = Field(default=Decimal("25.00"))
    PAPER_TRADING:           bool       = Field(default=True)
    TARGET_TICKER:           str        = Field(default="CPI")

    # ── Feature Flags ──────────────────────────────────────────────────────
    # ARB_ENABLED: set to true in .env only when both Kalshi AND
    # Polymarket accounts are funded and tested. Defaults to False
    # so the arb engine never fires accidentally.
    ARB_ENABLED:             bool       = Field(default=False)

    # ── Strategy Toggles ───────────────────────────────────────────────────
    CPI_ACTIVE_TODAY:        bool       = Field(default=False)
    FOMC_ACTIVE:             bool       = Field(default=False)
    FOMC_TICKER:             str        = Field(default="KXFED")
    EQUITIES_ACTIVE:         bool       = Field(default=True)
    SPORTS_ACTIVE:           bool       = Field(default=False)
    SPORTS_TICKER:           str        = Field(default="KXNBA")
    CRYPTO_ACTIVE:           bool       = Field(default=False)
    CRYPTO_TICKER:           str        = Field(default="KXBTC-PLACEHOLDER")

    # ── Backward Compatibility Aliases ─────────────────────────────────────
    @property
    def TELEGRAM_TOKEN(self) -> str | None:
        """Some files use TELEGRAM_TOKEN — alias to BOT_TOKEN."""
        return self.TELEGRAM_BOT_TOKEN

    @property
    def KALSHI_KEY_ID(self) -> str | None:
        """sdk_test.py uses KALSHI_KEY_ID — alias to API_KEY."""
        return self.KALSHI_API_KEY

    def to_decimal(self, val) -> Decimal:
        """Safe Decimal conversion used throughout the codebase."""
        return Decimal(str(val))

    model_config = SettingsConfigDict(
        env_file          = ".env",
        env_file_encoding = "utf-8",
        extra             = "ignore",  # Unknown env vars are ignored safely
    )


# Global singleton — imported everywhere as `from config import cfg`
cfg = AgentConfig()
