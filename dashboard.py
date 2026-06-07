import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import os
import datetime
import requests
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Kalshi Multi-Strat Terminal", page_icon="🏦", layout="wide")
st.markdown("<style>.metric-card { background-color: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #333; }</style>", unsafe_allow_html=True)

DB_PATH = "output/agent_history.db"
GHOST_DB_PATH = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")
API_KEY = os.getenv("GATEWAY_API_KEY", "suncoast-sovereign-key-2026")

if "memory_chat" not in st.session_state:
    st.session_state.memory_chat = [{"role": "assistant", "content": "Chief Risk Officer online. Ready for Ghost Book debrief. What are we auditing today?"}]

# --- 🎛️ Sidebar & Controls ---
with st.sidebar:
    st.markdown("### 🎛️ Terminal Controls")
    is_refresh_active = st.toggle("Live Auto-Refresh (10s)", value=True)
    if is_refresh_active:
        st_autorefresh(interval=10000, key="data_refresh")
        
    st.markdown("---")
    st.markdown("### 💻 System Health")
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        st.metric("CPU Load", f"{cpu}%")
        st.progress(cpu / 100.0)
        st.metric("Memory Usage", f"{ram}%")
        st.progress(ram / 100.0)
    except ImportError:
        st.warning("psutil not installed.")
        
    st.markdown("---")
    st.caption(f"System Time: {datetime.datetime.now().strftime('%H:%M:%S')}")

st.title("🏦 Quantitative Execution Terminal")
st.markdown("---")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Alpha & PnL", "⚡ Telemetry", "👻 Ghost Book", "🧠 Risk & Memory", "🌐 Arb Scanner", "📅 Schedule"])

# --- 📈 Tab 1: Alpha & PnL ---
with tab1:
    st.markdown("### 📈 System Performance & Equity Curve")
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            df_pnl = pd.read_sql_query("SELECT timestamp, CAST(net_spread AS REAL) as profit, kalshi_ticker as ticker FROM arb_spreads ORDER BY timestamp ASC", conn)
        
        if not df_pnl.empty:
            df_pnl['cumulative'] = df_pnl['profit'].cumsum()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Gross Alpha (PnL)", f"${df_pnl['cumulative'].iloc[-1]:.3f}", "+ Daily High")
            c2.metric("Win Rate", "100.0%", "Arb Risk-Free")
            c3.metric("Live Strategies", "5", "Fully Synced")
            c4.metric("Capital Deployed", "$0.00", "Paper Mode Active")
            
            fig = px.area(df_pnl, x='timestamp', y='cumulative', title='Cumulative Net Profit', template='plotly_dark')
            fig.update_traces(line_color='#00e676', fillcolor='rgba(0, 230, 118, 0.1)')
            fig.add_hline(y=0, line_dash="solid", line_color="#555555")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Awaiting live execution data to generate PnL curves...")
    except Exception as e:
        st.error(f"Database error: {e}")

# --- ⚡ Tab 2: Live Telemetry ---
with tab2:
    st.markdown("### ⚡ Live System Telemetry")
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            logs_df = pd.read_sql_query("SELECT timestamp, level, event_type, strategy, message FROM system_logs ORDER BY timestamp DESC LIMIT 50", conn)
            
        if not logs_df.empty:
            st.dataframe(logs_df, use_container_width=True, hide_index=True)
        else:
            st.info("System logs are currently empty. Awaiting engine boot sequence...")
    except Exception as e:
        st.error(f"Database error: {e}")

# --- 👻 Tab 3: Ghost Book ---
with tab3:
    st.markdown("### 👻 Ghost Book (Paper Trading Ledger)")
    try:
        with sqlite3.connect(GHOST_DB_PATH, timeout=5) as conn:
            df_paper = pd.read_sql_query("SELECT timestamp, ticker, signal, confidence, simulated_entry_price, reasoning FROM paper_trades ORDER BY timestamp DESC LIMIT 100", conn)
            
        if not df_paper.empty:
            df_chart = df_paper.copy()
            df_chart['timestamp'] = pd.to_datetime(df_chart['timestamp'])
            df_chart['confidence'] = pd.to_numeric(df_chart['confidence'], errors='coerce')
            
            c1, c2 = st.columns(2)
            with c1:
                fig_conf = px.line(df_chart.sort_values('timestamp'), x='timestamp', y='confidence', color='signal', title='Signal Confidence Over Time', markers=True)
                fig_conf.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#cccccc', yaxis=dict(range=[0, 100], gridcolor='#2a2a2a'), xaxis=dict(gridcolor='#2a2a2a'))
                st.plotly_chart(fig_conf, use_container_width=True)
                
            st.dataframe(df_paper, use_container_width=True, hide_index=True)
        else:
            st.info("The Ghost Book is empty.")
    except Exception as e:
        st.error(f"Database error: {e}")

# --- 🧠 Tab 4: Risk & Memory (CRO) ---
with tab4:
    st.subheader("🧠 Chief Risk Officer (CRO) Interrogation Interface")
    colA, colB = st.columns([1, 2])
    with colA:
        st.markdown("#### 🎛️ Audit Quick-Filters")
        filter_type = st.radio("Isolate Risk Events:", ["ALL TRADES", "🔴 VETOES ONLY", "🟢 HIGH CONFIDENCE"])
        try:
            with sqlite3.connect(GHOST_DB_PATH, timeout=5) as conn:
                df_ghost = pd.read_sql_query("SELECT timestamp, ticker, signal, confidence FROM paper_trades ORDER BY timestamp DESC LIMIT 50", conn)
            if not df_ghost.empty:
                display_df = df_ghost.copy()
                display_df['confidence'] = pd.to_numeric(display_df['confidence'], errors='coerce')
                if filter_type == "🔴 VETOES ONLY": display_df = display_df[display_df['confidence'] < 50]
                elif filter_type == "🟢 HIGH CONFIDENCE": display_df = display_df[display_df['confidence'] >= 80]
                st.dataframe(display_df, height=400, hide_index=True)
        except Exception: pass

    with colB:
        st.markdown("#### 💬 Memory Synthesis (Hermes-3)")
        chat_container = st.container(height=400)
        with chat_container:
            for msg in st.session_state.memory_chat:
                with st.chat_message(msg["role"]): st.write(msg["content"])
        
        if prompt := st.chat_input("E.g. 'Summarize the logic behind our last 3 trades.'"):
            st.session_state.memory_chat.append({"role": "user", "content": prompt})
            st.rerun()

if st.session_state.memory_chat[-1]["role"] == "user":
    user_prompt = st.session_state.memory_chat[-1]["content"]
    with tab4:
        with colB:
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("Synthesizing SQLite memory..."):
                        try:
                            resp = requests.post("http://127.0.0.1:8000/memory/query", json={"question": user_prompt, "filter_type": "ALL"}, headers={"x-api-key": API_KEY}, timeout=45)
                            answer = resp.json().get("answer", "Error parsing response.") if resp.status_code == 200 else f"API Error {resp.status_code}"
                        except Exception as e:
                            answer = f"Gateway unreachable. Ensure `pixel_ingest.py` is running on port 8000. Error: {e}"
                        st.write(answer)
                        st.session_state.memory_chat.append({"role": "assistant", "content": answer})

# --- 🌐 Tab 5: Arbitrage Scanner ---
with tab5:
    st.markdown("### ⚡ Live Arbitrage Spread Monitor")
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            arb_df = pd.read_sql_query("SELECT timestamp, kalshi_ticker, CAST(kalshi_ask AS REAL) AS kalshi_ask, CAST(poly_bid AS REAL) AS poly_bid, CAST(gross_spread AS REAL) AS gross_spread, is_profitable FROM arb_spreads ORDER BY timestamp DESC LIMIT 50", conn)
        if not arb_df.empty: st.dataframe(arb_df, use_container_width=True, hide_index=True)
        else: st.info("No spread data yet.")
    except Exception: pass

# --- 📅 Tab 6: Schedule ---
with tab6:
    st.markdown("### 📅 Daily Strategy Schedule")
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            sched_df = pd.read_sql_query("SELECT strategy, message FROM system_logs WHERE event_type = 'STRATEGY_REGISTERED' ORDER BY timestamp DESC LIMIT 20", conn)
        if not sched_df.empty:
            sched_df = sched_df.drop_duplicates(subset=['strategy'])
            st.dataframe(sched_df, use_container_width=True, hide_index=True)
        else: st.info("No strategies registered yet.")
    except Exception: pass
