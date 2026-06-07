import threading
from decimal import Decimal
from strategies.daily_equities import DailyEquitiesHunter

print("🚀 Forcing manual execution of EQUITIES_HUNTER...")
hunter = DailyEquitiesHunter()
lock = threading.Lock()

# Bypass capital allocation checks for the manual test
def mock_reserve(amount: Decimal) -> bool: return True
def mock_release(amount: Decimal): pass

try:
    hunter.execute(lock, mock_reserve, mock_release)
    print("\n✅ Execution complete. Check the Ghost Book tab in your UI!")
except Exception as e:
    print(f"\n❌ Error during execution: {e}")
