from kalshi_python_sync import ApiClient, Configuration
from kalshi_python_sync.api import exchange_api
from config import cfg

# Setup official config
configuration = Configuration()
configuration.key_id = cfg.KALSHI_KEY_ID
configuration.private_key_path = cfg.KALSHI_PRIVATE_KEY_PATH

# Initialize the client
api_client = ApiClient(configuration)
exchange = exchange_api.ExchangeApi(api_client)

try:
    status = exchange.get_exchange_status()
    print(f"✅ SDK CONNECTION SUCCESSFUL!")
    print(f"Exchange Status: {status.exchange_active}")
except Exception as e:
    print(f"❌ SDK CONNECTION FAILED: {e}")
