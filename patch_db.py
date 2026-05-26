import sqlite3
from config import cfg

try:
    conn = sqlite3.connect(cfg.DB_PATH)
    conn.execute("ALTER TABLE signals ADD COLUMN audit_notes TEXT;")
    conn.commit()
    print("✅ Database patched! 'audit_notes' column successfully added to the live database.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("✅ Database already has 'audit_notes'. We are good to go!")
    else:
        print(f"❌ SQL Error: {e}")
finally:
    conn.close()
