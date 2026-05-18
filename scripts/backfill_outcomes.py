"""
backfill_outcomes.py
Kalshi Agent v2.4 — Outcome Management CLI
Interactive tool to grade signals and update the win-rate for the Kelly Sizer.
"""

import sqlite3
import sys
from decimal import Decimal
from config import cfg

def run_backfill():
    print("\n--- 📊 Kalshi Agent: Outcome Backfill Tool ---")
    
    try:
        conn = sqlite3.connect(cfg.DB_PATH)
        cursor = conn.cursor()
        
        # 1. Fetch ungraded signals
        cursor.execute("""
            SELECT id, timestamp, ticker, signal, confidence, suggested_entry_dollars 
            FROM signals 
            WHERE outcome IS NULL OR outcome = ''
            ORDER BY timestamp ASC
        """)
        pending = cursor.fetchall()
        
        if not pending:
            print("✅ No pending signals to grade. You're all caught up!")
            return

        print(f"Found {len(pending)} ungraded signals.\n")

        for row in pending:
            s_id, ts, ticker, sig_type, conf, entry = row
            print(f"ID: {s_id} | {ticker} | {sig_type} at ${entry} ({conf}%)")
            
            choice = input("Result? [w]in, [l]oss, [s]kip, [q]uit: ").lower()
            
            if choice == 'q':
                break
            if choice == 's':
                print("Skipped.\n")
                continue
            
            outcome = "WIN" if choice == 'w' else "LOSS"
            
            # For Kalshi: WIN settles at 1.00, LOSS settles at 0.00
            # You can manually override if you exited early
            default_val = "1.00" if outcome == "WIN" else "0.00"
            val_input = input(f"Settled Value (default {default_val}): ")
            settled_val = val_input if val_input else default_val
            
            # 2. Update the DB
            cursor.execute("""
                UPDATE signals 
                SET outcome = ?, settled_value = ? 
                WHERE id = ?
            """, (outcome, settled_val, s_id))
            conn.commit()
            print(f"✅ Recorded {outcome} for Signal {s_id}\n")

        # 3. Calculate and show new Win Rate
        cursor.execute("SELECT outcome FROM signals WHERE outcome IS NOT NULL")
        all_outcomes = cursor.fetchall()
        if all_outcomes:
            wins = sum(1 for o in all_outcomes if o[0] == 'WIN')
            wr = (wins / len(all_outcomes)) * 100
            print(f"📈 New Lifetime Win Rate: {wr:.1f}% ({wins}/{len(all_outcomes)})")

        conn.close()

    except Exception as e:
        print(f"❌ Error accessing database: {e}")

if __name__ == "__main__":
    run_backfill()
