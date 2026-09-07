try:
    import urllib.request
    outbound_ip = urllib.request.urlopen(
        "https://api.ipify.org", timeout=10
    ).read().decode()
    print("RAILWAY OUTBOUND IP:", outbound_ip, flush=True)
except Exception as e:
    print("IP CHECK FAILED:", repr(e), flush=True)

try:
    url = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT"
    response = urllib.request.urlopen(url, timeout=10)
    print("DIRECT BYBIT TEST:", response.read().decode(), flush=True)
except Exception as e:
    print("DIRECT BYBIT TEST FAILED:", repr(e), flush=True)
    
from config import BOT_NAME
from notifier import send_message
from bybit_api import get_ticker

print(f"🚀 {BOT_NAME} Starting...")

response = get_ticker("BTCUSDT")

print("Ticker Response:")
print(response)

send_message("✅ Live market data received from Bybit!")

print("✅ Startup completed successfully.")
