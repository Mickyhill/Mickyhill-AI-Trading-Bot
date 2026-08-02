from config import BOT_NAME
from notifier import send_message
from bybit_api import test_connection

print(f"🚀 {BOT_NAME} Starting...")

response = test_connection()

print("Bybit Response:")
print(response)

send_message(f"🚀 {BOT_NAME} is ONLINE!")

print("✅ Startup completed successfully.")
