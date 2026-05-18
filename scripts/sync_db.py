"""
sync_db.py
Kalshi Agent v2.4 — Database Schema Migration
Adds missing columns to the signals table to support v2.4+ logic.
"""
import sqlite3
from config import cfg

def sync():
    print(f"📡 Connecting to {cfg.DB_PATH}...")
    conn = sqlite3.connect(cfg.DB_PATH)
    cursor = conn.cursor()
    
    # List of new columns to add
    new_columns = [
        ("suggested_entry_dollars", "TEXT"),
        ("risk_flag", "TEXT"),
        ("edge_source", "TEXT"),
        ("audit_notes", "TEXT")
    ]
    
    for col_name, col_type in new_columns:
        try:
            print(f"Adding column {col_name}...")
            cursor.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"✅ Added {col_name}")
        except sqlite3.OperationalError:
            print(f"ℹ️ Column {col_name} already exists. Skipping.")
            
    conn.close()
    print("✨ Database Sync Complete.")

if __name__ == "__main__":
    sync()
