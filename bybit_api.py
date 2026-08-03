from pybit.unified_trading import HTTP
import os

session = HTTP(
    testnet=False,
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
)

print("Bybit API module loaded successfully")


def get_server_time():
    return session.get_server_time()


def get_ticker(symbol="BTCUSDT"):
    return session.get_tickers(
        category="linear",
        symbol=symbol
    )
