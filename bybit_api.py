# Bybit API Connection

from pybit.unified_trading import HTTP
import os

session = HTTP(
    testnet=True,  # We'll use Testnet first for safety
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
)

print("Bybit API module loaded successfully.")
