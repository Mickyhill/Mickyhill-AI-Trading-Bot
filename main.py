
from config import BOT_NAME
from notifier import send_message
import bybit_api

print(f"🚀 {BOT_NAME} Starting...")

try:
    response = send_message(f"🚀 {BOT_NAME} is now ONLINE!")
    print(response)
except Exception as e:
    print("Telegram Error:", e)

print("✅ Startup completed successfully.")
