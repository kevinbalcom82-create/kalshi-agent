import os
import requests
from dotenv import load_dotenv

# Force load the .env file from the current directory
print("[*] Loading environment variables...")
load_dotenv(dotenv_path="/Users/npcforge/kalshi_agent/.env")

def test_telegram_connection():
    print("\n[*] Testing Telegram Bot Token...")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_new_bot_token_here":
        print("[-] SKIP: Telegram token not configured.")
        return

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            bot_data = response.json().get('result', {})
            print(f"[+] SUCCESS: Authenticated with Telegram as @{bot_data.get('username')}")
        else:
            print(f"[-] FAILED: Telegram auth failed. HTTP {response.status_code}")
    except Exception as e:
        print(f"[-] ERROR: Could not reach Telegram API: {e}")

def verify_kalshi_key_path():
    print("\n[*] Verifying Kalshi Private Key Path...")
    key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not key_path:
        print("[-] FAILED: KALSHI_PRIVATE_KEY_PATH not set in .env")
        return

    if os.path.exists(key_path):
        print(f"[+] SUCCESS: Found Kalshi PEM file at {key_path}")
        permissions = oct(os.stat(key_path).st_mode)[-3:]
        if int(permissions) > 600:
            print(f"[!] WARNING: File permissions ({permissions}) are too open. Run: chmod 600 {key_path}")
        else:
            print(f"[+] PERMISSIONS: {permissions} — correctly locked down.")
    else:
        print(f"[-] FAILED: No file found at {key_path}.")

def validate_polymarket_keys():
    print("\n[*] Validating Polymarket Key Structure...")
    key = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not key:
        print("[-] FAILED: POLYMARKET_PRIVATE_KEY not set")
    else:
        print(f"[+] SUCCESS: Polymarket private key detected (length: {len(key)})")

def check_critical_flags():
    print("\n[*] Checking Critical Strategy Flags...")
    flags = {
        "EXECUTION_MODE": os.getenv("EXECUTION_MODE"),
        "EQUITIES_ACTIVE": os.getenv("EQUITIES_ACTIVE"),
        "CRYPTO_ACTIVE": os.getenv("CRYPTO_ACTIVE"),
        "FOMC_ACTIVE": os.getenv("FOMC_ACTIVE"),
        "SPORTS_ACTIVE": os.getenv("SPORTS_ACTIVE"),
        "CPI_ACTIVE_TODAY": os.getenv("CPI_ACTIVE_TODAY"),
    }
    for key, val in flags.items():
        print(f"    {key} = {val}")

def check_data_providers():
    print("\n[*] Checking Data Provider Keys...")
    providers = {
        "FRED_API_KEY": os.getenv("FRED_API_KEY"),
        "BLS_API_KEY": os.getenv("BLS_API_KEY"),
        "POLYGON_API_KEY": os.getenv("POLYGON_API_KEY"),
        "NOAA_TOKEN": os.getenv("NOAA_TOKEN"),
        "ODDS_API_KEY": os.getenv("ODDS_API_KEY"),
    }
    for key, val in providers.items():
        status = "[+] SET" if val and "your_" not in val else "[-] MISSING"
        print(f"    {status}: {key}")

if __name__ == "__main__":
    print("=== SUNCOAST AGENT PRE-FLIGHT CHECK ===")
    test_telegram_connection()
    verify_kalshi_key_path()
    validate_polymarket_keys()
    check_data_providers()
    check_critical_flags()

    if os.getenv("CREWAI_TELEMETRY_OPT_OUT") == "true":
        print("\n[+] Privacy Check: Telemetry successfully opted OUT.")
    else:
        print("\n[!] Privacy Warning: CREWAI_TELEMETRY_OPT_OUT is not set to 'true'.")

    print("\n=== PRE-FLIGHT COMPLETE ===")
