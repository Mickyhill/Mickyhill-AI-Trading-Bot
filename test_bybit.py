import requests

urls = [
    "https://api.bybit.com/v5/market/time",
    "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=10",
]

for url in urls:
    print("\n" + "=" * 60)
    print(url)
    print("=" * 60)

    try:
        response = requests.get(
            url,
            timeout=30
        )

        print("STATUS:", response.status_code)
        print("RESPONSE:")
        print(response.text[:1000])

    except Exception as e:
        print("ERROR:", type(e).__name__)
        print(e)