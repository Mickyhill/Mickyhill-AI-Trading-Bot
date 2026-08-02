from pybit.unified_trading import HTTP
import os

session = HTTP(
    testnet=False,
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
)

print("Bybit API module loaded successfully")


def test_connection():
    try:
        response = session.get_wallet_balance(accountType="UNIFIED")
        return response
    except Exception as e:
        return str(e)
