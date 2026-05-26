import sqlite3, os

db_path = os.path.expanduser("~/kalshi_agent/output/ghost_book.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)
conn.execute('''
    CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        signal TEXT,
        confidence INTEGER,
        simulated_entry_price REAL,
        simulated_contracts INTEGER,
        edge_source TEXT,
        reasoning TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        outcome TEXT DEFAULT 'PENDING'
    )
''')
conn.commit()
conn.close()
print("👻 Ghost Book Database Initialized!")
