import sqlite3
from config import cfg

print(f"[*] Nuking old table at {cfg.DB_PATH}...")
try:
    with sqlite3.connect(cfg.DB_PATH, timeout=10) as conn:
        conn.execute("DROP TABLE IF EXISTS events;")
    print("✅ Database wiped! The logger will rebuild it cleanly on the next run.")
except Exception as e:
    print(f"❌ Error: {e} (You may need to stop your tmux agent briefly)")
