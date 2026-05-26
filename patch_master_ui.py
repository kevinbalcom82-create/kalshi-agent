import os

file_path = os.path.expanduser("~/kalshi_agent/scripts/dashboard.py")
with open(file_path, 'r') as f:
    content = f.read()

if "Ghost Book (Paper Trading Ledger)" not in content:
    with open(file_path, 'a') as f:
        f.write("\n\n# --- GHOST BOOK INJECTION ---\n")
        f.write("import pandas as pd\n")
        f.write("import sqlite3\n")
        f.write("import os\n")
        f.write("import streamlit as st\n\n")
        f.write("st.markdown('---')\n")
        f.write("st.subheader('👻 Ghost Book (Paper Trading Ledger)')\n\n")
        f.write("try:\n")
        f.write("    db_path = os.path.expanduser('~/kalshi_agent/output/ghost_book.db')\n")
        f.write("    conn = sqlite3.connect(db_path)\n")
        f.write("    df_paper = pd.read_sql_query(\n")
        f.write("        'SELECT timestamp, ticker, signal, confidence, outcome, simulated_entry_price, reasoning FROM paper_trades ORDER BY timestamp DESC LIMIT 50',\n")
        f.write("        conn\n")
        f.write("    )\n")
        f.write("    conn.close()\n\n")
        f.write("    if not df_paper.empty:\n")
        f.write("        st.dataframe(df_paper, use_container_width=True)\n")
        f.write("    else:\n")
        f.write("        st.info('The Ghost Book is currently empty. The engine is idling and waiting for setups.')\n\n")
        f.write("except Exception as e:\n")
        f.write("    st.error(f'Could not load Ghost Book data: {e}')\n")
    print("✅ Ghost Book successfully appended to the master dashboard!")
else:
    print("⚠️ Ghost Book is already in the master dashboard.")
