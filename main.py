from config import BOT_NAME
from notifier import send_message
from bybit_api import get_ticker

print(f"🚀 {BOT_NAME} Starting...")

response = get_ticker("BTCUSDT")

print("Ticker Response:")
print(response)

send_message("✅ Live market data received from Bybit!")

print("✅ Startup completed successfully.")
