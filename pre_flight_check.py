import os
import sys
from config import cfg

def check():
    print("🔍 RUNNING PRE-FLIGHT SYNC CHECK...")
    errors = 0

    # 1. Check Files on Disk
    required_files = [
        '.env', 
        '.kalshi_key.pem', 
        'config.py', 
        'core_engine.py', 
        'data/kalshi_stream.py',
        'state/market_state.py',
        'state/context_builder.py',
        'engine/signal_engine.py',
        'output/telegram_notifier.py'
    ]
    print("\n📁 Checking File Structure:")
    for f in required_files:
        if os.path.exists(f):
            print(f"  ✅ {f} exists.")
        else:
            print(f"  ❌ MISSING: {f}")
            errors += 1

    # 2. Check Config & Env
    print("\n🔑 Checking Credentials (Sanitized):")
    creds = {
        "KALSHI_KEY_ID": cfg.KALSHI_KEY_ID,
        "PEM_PATH": cfg.KALSHI_PRIVATE_KEY_PATH,
        "GEMINI_KEY": cfg.GEMINI_API_KEY,
        "TELEGRAM_BOT": cfg.TELEGRAM_TOKEN
    }
    for name, val in creds.items():
        if val:
            # Show first 4 chars for verification
            print(f"  ✅ {name}: Found (Starts with: {str(val)[:4]}...)")
        else:
            print(f"  ❌ {name}: NOT FOUND in .env or Config")
            errors += 1

    # 3. Check PEM Accessibility
    if cfg.KALSHI_PRIVATE_KEY_PATH and os.path.exists(cfg.KALSHI_PRIVATE_KEY_PATH):
        try:
            with open(cfg.KALSHI_PRIVATE_KEY_PATH, 'r') as f:
                content = f.read()
                if "BEGIN RSA PRIVATE KEY" in content:
                    print("  ✅ PEM File: Valid RSA Header found.")
                else:
                    print("  ❌ PEM File: RSA Header missing!")
                    errors += 1
        except Exception as e:
            print(f"  ❌ PEM File: Not readable - {e}")
            errors += 1

    # 4. Check Import Integrity
    print("\n🔗 Checking Component Integration:")
    try:
        from output.telegram_notifier import send_telegram
        print("  ✅ Telegram Notifier: send_telegram found.")
    except Exception as e:
        print(f"  ❌ Telegram Notifier: Import failed - {e}")
        errors += 1

    try:
        from state.market_state import state_manager
        print(f"  ✅ Market State: state_manager found ({type(state_manager).__name__}).")
    except Exception as e:
        print(f"  ❌ Market State: Import failed - {e}")
        errors += 1

    try:
        from engine.signal_engine import generate_signal
        print("  ✅ Signal Engine: generate_signal found.")
    except Exception as e:
        print(f"  ❌ Signal Engine: Import failed - {e}")
        errors += 1

    try:
        from data.kalshi_stream import KalshiStream
        print("  ✅ Kalshi Stream: KalshiStream class found.")
    except Exception as e:
        print(f"  ❌ Kalshi Stream: Import failed - {e}")
        errors += 1

    print("\n" + "="*30)
    if errors == 0:
        print("🚀 SYNC COMPLETE: System is ready for a clean run.")
    else:
        print(f"🛑 SYNC FAILED: {errors} issues found. Fix these before running core_engine.py.")
    print("="*30)

if __name__ == "__main__":
    check()
