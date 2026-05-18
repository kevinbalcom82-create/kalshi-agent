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
