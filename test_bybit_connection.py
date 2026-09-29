import requests
import time

URL = "https://api.bybit.com/v5/market/time"

print("=" * 60)
print("BYBIT CONNECTION TEST")
print("=" * 60)

for attempt in range(1, 4):

    print(f"\nAttempt {attempt}/3...")

    try:
        start = time.time()

        response = requests.get(
            URL,
            timeout=30
        )

        elapsed = time.time() - start

        print(f"Status code: {response.status_code}")
        print(f"Response time: {elapsed:.2f} seconds")
        print(f"Response: {response.text[:500]}")

    except Exception as e:

        print(f"ERROR: {type(e).__name__}")
        print(f"DETAIL: {e}")

    time.sleep(2)

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)