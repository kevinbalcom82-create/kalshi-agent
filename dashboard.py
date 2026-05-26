import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from config import cfg

# Force Dark Mode & Wide Layout
st.set_page_config(page_title="Kalshi Sniper UI", layout="wide", initial_sidebar_state="collapsed")

def load_data():
    try:
        conn = sqlite3.connect(cfg.DB_PATH, timeout=5)
        # Load Logs
        logs_df = pd.read_sql_query("SELECT timestamp, level, event_type, message FROM events ORDER BY id DESC LIMIT 50", conn)
        # Load Trades
        trades_df = pd.read_sql_query("SELECT timestamp, ticker, side, contracts, status, price_filled FROM trade_orders ORDER BY id DESC", conn)
        conn.close()
        return logs_df, trades_df
    except Exception as e:
        st.error(f"Database Locked or Missing: {e}")
        return pd.DataFrame(), pd.DataFrame()

st.title("🎯 Kalshi Sniper: Command Center")
st.markdown(f"**Target:** `{cfg.TARGET_TICKER}` | **Bankroll:** `${cfg.BANKROLL}`")

logs, trades = load_data()

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 Execution Ledger")
    if not trades.empty:
        st.dataframe(trades, use_container_width=True, hide_index=True)
    else:
        st.info("No trades executed yet. Awaiting trigger...")

with col2:
    st.subheader("⚙️ Live System Logs")
    if not logs.empty:
        for _, row in logs.head(10).iterrows():
            color = "🔴" if row['level'] in ['ERROR', 'CRITICAL'] else "🟡" if row['level'] == 'WARNING' else "🟢"
            st.markdown(f"**{color} {row['event_type']}**\n\n`{row['timestamp'][:19]}` - {row['message']}")
            st.divider()

# Auto-refresh button
if st.button("🔄 Refresh Data"):
    st.rerun()

# --- GHOST BOOK INJECTION ---
import pandas as pd
import sqlite3
try:
    from config import cfg
except ImportError:
    pass

st.markdown('---')
st.subheader('👻 Ghost Book (Paper Trading Ledger)')
try:
    conn = sqlite3.connect(cfg.DB_PATH)
    df_paper = pd.read_sql_query('SELECT timestamp, ticker, signal, confidence, outcome, simulated_contracts, reasoning FROM paper_trades ORDER BY timestamp DESC LIMIT 50', conn)
    conn.close()
    if not df_paper.empty:
        st.dataframe(df_paper, use_container_width=True)
    else:
        st.info('The Ghost Book is currently empty. Engine is idling and waiting for setups.')
except Exception as e:
    st.error(f'Could not load Ghost Book data: {e}')
# --- GHOST BOOK INJECTION ---
import pandas as pd
import sqlite3
import os
import streamlit as st

st.markdown("---")
st.subheader("👻 Ghost Book (Paper Trading Ledger)")

try:
    # Point directly to the Ghost Book database
    db_path = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")
    
    conn = sqlite3.connect(db_path)
    df_paper = pd.read_sql_query(
        "SELECT timestamp, ticker, signal, confidence, outcome, simulated_entry_price, reasoning FROM paper_trades ORDER BY timestamp DESC LIMIT 50", 
        conn
    )
    conn.close()

    if not df_paper.empty:
        # Display the dataframe taking up the full width of your UI
        st.dataframe(df_paper, use_container_width=True)
    else:
        st.info("The Ghost Book is currently empty. The engine is idling and waiting for setups.")

except Exception as e:
    st.error(f"Could not load Ghost Book data: {e}")