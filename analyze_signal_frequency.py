# ==========================================
# ONE-TIME ANALYSIS SCRIPT
#
# Answers the real question: across your 120-day
# backtest, on how many distinct 15-minute moments
# did AT LEAST ONE of your 15 symbols have a
# qualifying setup? That's the true, fair number
# to compare against "zero signals in one live day"
# — not the raw 743-trade count, which counted each
# symbol independently and doesn't match how the
# live bot actually picks just one winner per scan.
#
# Uses your EXISTING historical_data cache — no new
# downloads, no network needed.
# ==========================================

import os
import json

from backtester import (
    SYMBOLS, LOOKBACK_DAYS, END_OFFSET_DAYS,
    ms, sort_oldest_first, window_ending_at,
    find_index_at_or_before, get_direction_at,
)
from strategy import evaluate_setup
import time


def load_cache_only(symbol, interval):
    path = os.path.join("historical_data", f"{symbol}_{interval}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def prepare_from_cache(symbol):
    raw_15m = load_cache_only(symbol, "15")
    raw_1h = load_cache_only(symbol, "60")
    raw_4h = load_cache_only(symbol, "240")

    if raw_15m is None or raw_1h is None or raw_4h is None:
        return None

    return {
        "15m": sort_oldest_first(raw_15m),
        "1h": sort_oldest_first(raw_1h),
        "4h": sort_oldest_first(raw_4h),
    }


def main():
    now_ms_val = int(time.time() * 1000) - ms(END_OFFSET_DAYS)
    test_start_ms = now_ms_val - ms(LOOKBACK_DAYS)

    print("Loading cached data for all symbols (no network needed)...")

    btc_data = prepare_from_cache("BTCUSDT")
    if btc_data is None:
        print("❌ No cached BTCUSDT data found. Run backtester.py at least once first.")
        return

    symbol_data = {}
    for symbol in SYMBOLS:
        data = prepare_from_cache(symbol)
        if data is None:
            print(f"⚠️ No cached data for {symbol}, skipping it in this analysis.")
            continue
        symbol_data[symbol] = data

    if not symbol_data:
        print("❌ No cached symbol data found at all.")
        return

    print(f"Loaded {len(symbol_data)} symbols from cache.\n")

    # Use the shortest available 15m series as the shared timeline
    reference_symbol = next(iter(symbol_data))
    ref_15m = symbol_data[reference_symbol]["15m"]

    start_index = find_index_at_or_before(ref_15m, test_start_ms)
    if start_index == -1:
        print("❌ Not enough cached history to analyze.")
        return

    end_index = len(ref_15m) - 1

    moments_with_signal = 0
    total_moments = 0

    print("Scanning every 15-minute moment across the test window...")
    print("(this may take a minute — it's re-running the same analysis")
    print("as the backtest, just checking 'did ANYTHING qualify' instead")
    print("of tracking full trade outcomes)\n")

    for i in range(start_index, end_index + 1):

        timestamp = int(ref_15m[i][0])
        total_moments += 1

        btc_a15, btc_a1h, btc_a4h = get_direction_at(
            btc_data,
            find_index_at_or_before(btc_data["15m"], timestamp),
            timestamp,
        )

        if btc_a15 is None:
            btc_direction = "WAIT"
        elif (
            btc_a15["DIRECTION"] == btc_a1h["DIRECTION"]
            and btc_a1h["DIRECTION"] == btc_a4h["DIRECTION"]
        ):
            btc_direction = btc_a1h["DIRECTION"]
        else:
            btc_direction = "WAIT"

        found_one = False

        for symbol, data in symbol_data.items():

            idx_15m = find_index_at_or_before(data["15m"], timestamp)
            if idx_15m == -1:
                continue

            a15, a1h, a4h = get_direction_at(data, idx_15m, timestamp)

            if a15 is None:
                continue

            analysis, reason = evaluate_setup(a15, a1h, a4h, btc_direction)

            if analysis is not None:
                found_one = True
                break  # one is enough — we just need "at least one"

        if found_one:
            moments_with_signal += 1

    days_covered = LOOKBACK_DAYS
    rate_per_day = (moments_with_signal / days_covered) if days_covered else 0

    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Total 15-minute moments checked: {total_moments}")
    print(f"Moments where AT LEAST ONE symbol qualified: {moments_with_signal}")
    print(f"That's roughly {rate_per_day:.2f} qualifying moments PER DAY")
    print()
    print("This is the fair number to compare against your live bot's")
    print("actual signal rate — not the raw 743-trade backtest count.")


if __name__ == "__main__":
    main()