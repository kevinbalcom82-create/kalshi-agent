import os
import glob

# 1. Search the directory for the Streamlit file
agent_dir = os.path.expanduser("~/kalshi_agent")
py_files = glob.glob(os.path.join(agent_dir, "*.py")) + glob.glob(os.path.join(agent_dir, "output/*.py"))

streamlit_file = None
for f in py_files:
    try:
        with open(f, 'r') as file:
            if "import streamlit" in file.read():
                streamlit_file = f
                break
    except:
        continue

# 2. Safely inject the Ghost Book UI block
if streamlit_file:
    with open(streamlit_file, 'r') as file:
        content = file.read()
    
    if "paper_trades" not in content:
        print(f"🔍 Found Streamlit app at: {streamlit_file}")
        print("⚙️ Injecting Ghost Book UI module...")
        
        with open(streamlit_file, 'a') as file:
            file.write("\n\n# --- GHOST BOOK INJECTION ---\n")
            file.write("import pandas as pd\n")
            file.write("import sqlite3\n")
            file.write("try:\n")
            file.write("    from config import cfg\n")
            file.write("except ImportError:\n")
            file.write("    pass\n\n")
            file.write("st.markdown('---')\n")
            file.write("st.subheader('👻 Ghost Book (Paper Trading Ledger)')\n")
            file.write("try:\n")
            file.write("    conn = sqlite3.connect(cfg.DB_PATH)\n")
            file.write("    df_paper = pd.read_sql_query('SELECT timestamp, ticker, signal, confidence, outcome, simulated_contracts, reasoning FROM paper_trades ORDER BY timestamp DESC LIMIT 50', conn)\n")
            file.write("    conn.close()\n")
            file.write("    if not df_paper.empty:\n")
            file.write("        st.dataframe(df_paper, use_container_width=True)\n")
            file.write("    else:\n")
            file.write("        st.info('The Ghost Book is currently empty. Engine is idling and waiting for setups.')\n")
            file.write("except Exception as e:\n")
            file.write("    st.error(f'Could not load Ghost Book data: {e}')\n")
            
        print("✅ Success! Ghost Book module appended.")
    else:
        print("⚠️ Ghost Book logic is already present in your Streamlit app.")
else:
    print("❌ Could not automatically locate the Streamlit Python file. Ensure it is inside ~/kalshi_agent.")
