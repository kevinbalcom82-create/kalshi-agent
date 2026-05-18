import os
import sys
from dotenv import load_dotenv
load_dotenv()
from config import cfg

def check():
    print("🔍 RUNNING PRE-FLIGHT SYNC CHECK...")
    errors = 0

    required_files = [
        '.env', '.kalshi_key.pem', 'config.py', 'core_engine.py', 
        'data/kalshi_stream.py', 'state/market_state.py',
        'engine/signal_engine.py', 'output/telegram_notifier.py'
    ]
    print("\n📁 Checking File Structure:")
    for f in required_files:
        if os.path.exists(f): print(f"  ✅ {f} exists.")
        else: 
            print(f"  ❌ MISSING: {f}")
            errors += 1

    print("\n🔑 Checking Credentials (Sanitized):")
    # Matches your exact .env spelling
    kalshi_key = getattr(cfg, "KALSHI_API_KEY", None) or os.getenv("KALSHI_API_KEY")
    
    if kalshi_key: print(f"  ✅ KALSHI_API_KEY: Found (Starts with: {str(kalshi_key)[:4]}...)")
    else: 
        print("  ❌ KALSHI_API_KEY: NOT FOUND in .env or Config")
        errors += 1

    if cfg.KALSHI_PRIVATE_KEY_PATH and os.path.exists(cfg.KALSHI_PRIVATE_KEY_PATH):
        try:
            with open(cfg.KALSHI_PRIVATE_KEY_PATH, 'r') as f:
                if "PRIVATE KEY" in f.read(): print("  ✅ PEM File: Valid Header found.")
                else: 
                    print("  ❌ PEM File: Header missing!")
                    errors += 1
        except Exception as e:
            print(f"  ❌ PEM File: Not readable - {e}")
            errors += 1

    tel_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if tel_token: print(f"  ✅ TELEGRAM_BOT: Found (Starts with: {str(tel_token)[:4]}...)")
    else:
        print("  ❌ TELEGRAM_BOT: NOT FOUND")
        errors += 1

    print("\n🔗 Checking Component Integration:")
    try: from output.telegram_notifier import send_telegram; print("  ✅ Telegram Notifier OK.")
    except Exception as e: print(f"  ❌ Telegram Notifier FAIL: {e}"); errors += 1
    
    try: from state.market_state import state_manager; print("  ✅ Market State OK.")
    except Exception as e: print(f"  ❌ Market State FAIL: {e}"); errors += 1

    print("\n" + "="*30)
    if errors == 0: print("🚀 SYNC COMPLETE: System is ready for a clean run.")
    else: print(f"🛑 SYNC FAILED: {errors} issues found.")
    print("="*30)

if __name__ == "__main__":
    check()
