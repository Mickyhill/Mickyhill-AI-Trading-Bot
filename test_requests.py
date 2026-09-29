import requests

try:
    r = requests.get("https://api.bybit.com/v5/market/time", timeout=30)
    print(r.status_code)
    print(r.text)
except Exception as e:
    print(e)