from kalshi_python_sync.api_client import ApiClient
from kalshi_python_sync.configuration import Configuration
from kalshi_python_sync.api import exchange_api
from config import cfg

# Setup official config
configuration = Configuration()
configuration.key_id = getattr(cfg, "KALSHI_KEY_ID", None)
configuration.private_key_path = getattr(cfg, "KALSHI_PRIVATE_KEY_PATH", None)

# Initialize the client
api_client = ApiClient(configuration)
exchange = exchange_api.ExchangeApi(api_client)

try:
    status = exchange.get_exchange_status()
    print(f"✅ SDK CONNECTION SUCCESSFUL!")
    print(f"Exchange Status: {status.exchange_active}")
except Exception as e:
    print(f"❌ SDK CONNECTION FAILED: {e}")
