"""
integration_patches.py
Shows exactly which lines to change in your existing files.
These are NOT standalone scripts — they show the diffs to apply.
"""

# ─────────────────────────────────────────────────────────────────────────────
# PATCH 1: context_builder.py
# Add OBI signal to the existing prompt assembly.
# Find the "## MARKET STATE" section (around line 60) and add after the
# Kalshi block section. The yes_levels and no_levels come from the
# snapshot that state_manager already has.
# ─────────────────────────────────────────────────────────────────────────────

CONTEXT_BUILDER_PATCH = '''
# At the top of context_builder.py, add this import:
from engine.orderbook_imbalance import obi_analyzer

# Inside build_context(), after the "Kalshi Block" prompt section,
# add this block:

    # OBI Block (new)
    kalshi_state = state_manager.get_or_create(ticker)
    yes_levels = getattr(kalshi_state, 'yes_levels', [])
    no_levels  = getattr(kalshi_state, 'no_levels', [])

    obi_block = obi_analyzer.build_prompt_block(yes_levels, no_levels)
    if obi_block:
        prompt_sections.append(obi_block)

# Also add "OBI" as a valid edge_source in the output format string:
# "edge_source": "FRED" | "BLS" | "ORDERBOOK" | "SENTIMENT" | "OBI"
'''


# ─────────────────────────────────────────────────────────────────────────────
# PATCH 2: market_state.py
# MarketState currently stores yes_bid, yes_ask, price as scalars.
# We need it to also store the full price levels list from apply_snapshot.
# Add two attributes and update apply_snapshot.
# ─────────────────────────────────────────────────────────────────────────────

MARKET_STATE_PATCH = '''
# In MarketState.__init__(), add:
        self.yes_levels = []   # list of (price, size) tuples — bid side
        self.no_levels  = []   # list of (price, size) tuples — ask side

# In MarketState.apply_snapshot(), update to store levels:
    def apply_snapshot(self, data: dict):
        with self._lock:
            self.snapshot_loaded = True
            self.last_update = datetime.utcnow()

            # Store full depth for OBI calculation (NEW)
            yes_raw = data.get("yes_dollars_fp", [])
            no_raw  = data.get("no_dollars_fp", [])
            self.yes_levels = [(p, s) for p, s in yes_raw] if yes_raw else []
            self.no_levels  = [(p, s) for p, s in no_raw]  if no_raw  else []
'''


# ─────────────────────────────────────────────────────────────────────────────
# PATCH 3: strategies/daily_equities.py
# Wire VRP into DailyEquitiesHunter.build_context().
# yfinance already fetches VIX — we just need SPX price history too.
# ─────────────────────────────────────────────────────────────────────────────

DAILY_EQUITIES_PATCH = '''
# At the top of daily_equities.py, add:
from engine.vrp_analyzer import vrp_analyzer

# In build_context(), after the existing yfinance calls, add:

        # Fetch SPX price history for realized vol calculation (20 trading days)
        spx_history_prices = []
        try:
            import yfinance as yf
            spx_raw = yf.Ticker("^GSPC").history(period="25d")
            spx_history_prices = list(reversed(spx_raw["Close"].tolist()))
        except Exception:
            pass  # VRP block will be skipped gracefully

        # Build VRP block
        vrp_block = vrp_analyzer.build_prompt_block(vix, spx_history_prices)

# Then add vrp_block to prompt_sections:
        if vrp_block:
            prompt_sections.append(vrp_block)

# Also update edge_source options in the output format block:
# "edge_source": "VIX" | "TREND" | "SENTIMENT" | "MOMENTUM" | "VRP"
'''

# Print a summary
print("=" * 60)
print("INTEGRATION SUMMARY")
print("=" * 60)
print()
print("New files to add to your project:")
print("  engine/orderbook_imbalance.py  — OBI calculator")
print("  engine/vrp_analyzer.py         — VRP calculator")
print()
print("Files to patch:")
print("  state/market_state.py          — store full book depth")
print("  state/context_builder.py       — inject OBI prompt block")
print("  strategies/daily_equities.py   — inject VRP prompt block")
print()
print("Files NOT changed (intentionally):")
print("  engine/brain.py                — LLM prompt handling unchanged")
print("  engine/cro_auditor.py          — audit rules unchanged")
print("  engine/kelly_sizer.py          — sizing unchanged")
print("  engine/kalshi_router.py        — execution unchanged")
print()
print("Zero new pip dependencies for OBI (pure stdlib + your existing code).")
print("VRP needs: yfinance (already in your stack).")

