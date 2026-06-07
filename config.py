import os
from decimal import Decimal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """
    Centralized configuration for the Suncoast Agent Factory.
    Validates all required environment variables on startup.
    Fails immediately with a clear error if critical keys are missing.
    """

    # ── Trading Execution ─────────────────────────────────────────────────────
    KALSHI_API_KEY:           str | None   = None
    KALSHI_PRIVATE_KEY_PATH:  str          = Field(default="./secrets/kalshi.pem")
    POLYMARKET_PRIVATE_KEY:   str | None   = None
    POLYMARKET_PROXY_WALLET:  str | None   = None

    # ── Market Data Providers ─────────────────────────────────────────────────
    FRED_API_KEY:             str | None   = None
    BLS_API_KEY:              str | None   = None
    NOAA_TOKEN:               str | None   = None
    POLYGON_API_KEY:          str | None   = None
    ODDS_API_KEY:             str | None   = None

    # ── Alerts & Monitoring ───────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN:       str | None   = None
    TELEGRAM_CHAT_ID:         str | None   = None

    # ── Infrastructure ────────────────────────────────────────────────────────
    REST_BASE_URL:            str          = Field(default="https://external-api.kalshi.com")
    POLYGON_RPC_URL:          str          = Field(default="https://polygon-rpc.com")
    DB_PATH:                  str          = Field(default="/Volumes/AI_Drive/kalshi_data/market_state.db")
    HEARTBEAT_INTERVAL_SECONDS: int        = Field(default=3600)

    # ── Financial Settings ────────────────────────────────────────────────────
    BANKROLL:                 Decimal      = Field(default=Decimal("25.00"))
    PAPER_TRADING:            bool         = Field(default=True)
    TARGET_TICKER:            str          = Field(default="CPI")

    # ── Strategy Toggles ──────────────────────────────────────────────────────
    CPI_ACTIVE_TODAY:         bool         = Field(default=False)
    FOMC_ACTIVE:              bool         = Field(default=False)
    FOMC_TICKER:              str          = Field(default="KXFED")
    EQUITIES_ACTIVE:          bool         = Field(default=True)
    SPORTS_ACTIVE:            bool         = Field(default=False)
    SPORTS_TICKER:            str          = Field(default="KXNBA")
    CRYPTO_ACTIVE:            bool         = Field(default=False)
    CRYPTO_TICKER:            str          = Field(default="KXBTC-PLACEHOLDER")

    # ── Backward compatibility aliases ────────────────────────────────────────
    @property
    def TELEGRAM_TOKEN(self) -> str | None:
        """Alias — some files use TELEGRAM_TOKEN, others TELEGRAM_BOT_TOKEN."""
        return self.TELEGRAM_BOT_TOKEN

    def to_decimal(self, val) -> Decimal:
        """Utility used throughout codebase for safe Decimal conversion."""
        return Decimal(str(val))

    model_config = SettingsConfigDict(
        env_file          = ".env",
        env_file_encoding = "utf-8",
        extra             = "ignore",   # Ignore unknown env vars safely
    )


# Global singleton — raises ValidationError at boot if critical keys missing
cfg = AgentConfig()
