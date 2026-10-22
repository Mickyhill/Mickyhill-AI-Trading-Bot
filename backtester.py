# ==========================================
# MickyHill AI Trading Bot
# backtester.py
#
# Replays historical price data through the exact
# same evaluate_setup() logic used live, to see
# whether the strategy would have actually made
# money over the past N days.
#
# IMPORTANT FIX (see the professional audit / the
# scan_market() fix in main.py for full context):
#
# The previous version of this file tested every
# symbol completely independently, in isolation --
# effectively simulating 15 separate bots each with
# their own full account risk, all running at once.
# The live bot has never worked that way: main.py's
# scan_market() looks at ALL symbols together on each
# scan and opens at most ONE new trade per scan, the
# single highest-scoring qualifying setup across the
# whole symbol list, while any other already-open
# trades keep running until they hit TP2 or stop.
#
# This version instead walks forward through a single
# shared 15-minute timeline across every symbol at
# once, mirroring that exact selection rule: at each
# tick, existing open trades are checked for a TP2/
# stop hit first, then -- if a slot is free -- the
# single best-scoring qualifying candidate across all
# symbols this tick (that doesn't already have an open
# trade) is opened, exactly like scan_market() does.
# Exits are TP2-only, matching the fixed paper_monitor.py.
#
# LOOK-AHEAD FIX (closed candles only):
#
# A tick's timestamp is the START of a 15m candle. The
# decision for that tick happens when the 15m candle
# CLOSES, 15 minutes later. The old version picked the
# 1H and 4H candle whose START was at or before the tick,
# so a 1H candle up to 45 minutes from finishing (and a
# 4H candle up to 3h45m from finishing) got used, closing
# price included. The strategy saw prices from the future.
# get_direction_at() now only uses 1H and 4H candles that
# have fully closed by the decision time, matching the
# live bot after the bybit_api.get_kline() closed-candle fix.
# ==========================================


import time
import os
import json

import config

from bybit_api import get_kline_history
from analyzer import analyze_market
from strategy import evaluate_setup


# ==========================================
# LOCAL HISTORICAL DATA CACHE
# ==========================================

DATA_DIR = "historical_data"


def get_cache_path(symbol, interval):
    os.makedirs(DATA_DIR, exist_ok=True)

    return os.path.join(
        DATA_DIR,
        f"{symbol}_{interval}.json"
    )


def save_cached_data(symbol, interval, rows):
    path = get_cache_path(symbol, interval)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)

    print(
        f"  💾 Saved {len(rows)} candles to {path}"
    )


def load_cached_data(symbol, interval):
    path = get_cache_path(symbol, interval)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = json.load(f)

        if not rows:
            return None

        print(
            f"  📂 Loaded {len(rows)} candles from {path}"
        )

        return rows

    except Exception as e:
        print(
            f"  ⚠️ Could not load cache {path}: {e}"
        )

        return None


# ==========================================
# SETTINGS
# ==========================================

SYMBOLS = [
    # Original 5 -- already validated, keep for continuity
    "SOLUSDT",
    "LINKUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LTCUSDT",

    # New: established, liquid mid-caps -- NOT hand-picked from
    # what already fired live, to avoid survivorship bias
    "DOTUSDT",
    "ATOMUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "FILUSDT",
    "INJUSDT",
    "SUIUSDT",
    "ETCUSDT",
]

LOOKBACK_DAYS = 120

# Shifts the whole test window back in time. 0 = the most recent
# LOOKBACK_DAYS (today backward). Set this to test an OLDER period
# instead -- e.g. END_OFFSET_DAYS = 180 tests the 120 days ending
# 180 days ago, so you can check whether the strategy performs
# differently in a different market regime (e.g. an uptrend period)
# rather than only ever testing the most recent stretch.
END_OFFSET_DAYS = 0

# Extra history fetched BEFORE the test window so
# indicators (EMA50, ADX, etc.) have enough data to
# be accurate from day 1 of the actual test period.
WARMUP_DAYS_15M = 10
WARMUP_DAYS_1H = 15
WARMUP_DAYS_4H = 30

# How many candles to feed analyze_market each time
# (matches the live bot's default window size)
WINDOW_SIZE = 250

# How long to let a trade run before giving up on it
MAX_HOLDING_BARS_15M = 384  # 384 * 15min = 4 days

# Round-trip fee estimate (open + close), as a decimal
ROUND_TRIP_FEE_PCT = 0.0012  # 0.12%


# ==========================================
# HELPERS: TIME WINDOWS
# ==========================================

def ms(days):
    return int(days * 24 * 60 * 60 * 1000)


# Candle lengths in milliseconds
MS_15M = 15 * 60 * 1000
MS_1H = 60 * 60 * 1000
MS_4H = 4 * 60 * 60 * 1000


def sort_oldest_first(rows):
    """Bybit returns newest-first. Backtesting is easier
    with oldest-first, indexable arrays."""
    return sorted(rows, key=lambda r: int(r[0]))


def window_ending_at(oldest_first_rows, end_index, size=WINDOW_SIZE):
    """
    Returns up to `size` candles ending at end_index (inclusive),
    in NEWEST-FIRST order (what analyze_market expects, since it
    reverses internally to match live Bybit responses).
    """
    start_index = max(0, end_index - size + 1)
    window = oldest_first_rows[start_index:end_index + 1]
    return list(reversed(window))


def find_index_at_or_before(oldest_first_rows, target_time_ms):
    """
    Binary search: returns the index of the latest candle whose
    startTime is <= target_time_ms. Returns -1 if none qualify.
    """
    lo, hi = 0, len(oldest_first_rows) - 1
    result = -1

    while lo <= hi:
        mid = (lo + hi) // 2
        candle_time = int(oldest_first_rows[mid][0])

        if candle_time <= target_time_ms:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1

    return result


# ==========================================
# TRADE OUTCOME HELPERS
#
# One candle at a time, driven by the shared timeline loop in
# run_backtest() below -- NOT a per-trade look-ahead scan. This is
# what lets multiple symbols' trades be open and checked together,
# on the same footing the live bot actually runs on.
# ==========================================

def _hit_stop_or_target(direction, high, low, stop_loss, target):
    """
    Conservative same-candle tie-break: if a single candle's range
    touches BOTH stop and target, assume stop-loss was hit first
    (worst case) -- same rule the old simulate_trade_outcome() used.

    Returns "stop", "target", or None.
    """
    if direction == "BUY":
        hit_stop = low <= stop_loss
        hit_target = high >= target
    else:  # SELL
        hit_stop = high >= stop_loss
        hit_target = low <= target

    if hit_stop:
        return "stop"
    if hit_target:
        return "target"
    return None


def _pnl_pct(direction, entry, exit_price, fee_pct=ROUND_TRIP_FEE_PCT):
    if direction == "BUY":
        return (exit_price - entry) / entry - fee_pct
    return (entry - exit_price) / entry - fee_pct


# ==========================================
# STATS AGGREGATION
# ==========================================

def compute_stats(trades):
    """
    trades: list of dicts with at least "result" and "pnl_pct".
    TIMEOUT trades are reported separately and excluded from the
    core win/loss statistics (their real outcome is unknown).
    """

    closed = [t for t in trades if t["result"] in ("WIN", "LOSS")]
    timeouts = [t for t in trades if t["result"] == "TIMEOUT"]

    wins = [t for t in closed if t["result"] == "WIN"]
    losses = [t for t in closed if t["result"] == "LOSS"]

    n = len(closed)

    if n == 0:
        return {
            "num_trades": 0,
            "num_timeouts": len(timeouts),
            "message": "No closed trades to analyze.",
        }

    win_rate = len(wins) / n
    loss_rate = len(losses) / n

    avg_win = (
        sum(t["pnl_pct"] for t in wins) / len(wins)
        if wins else 0.0
    )
    avg_loss = (
        sum(t["pnl_pct"] for t in losses) / len(losses)
        if losses else 0.0
    )

    gross_win = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))

    profit_factor = (
        gross_win / gross_loss if gross_loss > 0 else float("inf")
    )

    expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)

    # Max drawdown on cumulative pnl curve
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for t in closed:
        cumulative += t["pnl_pct"]
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_drawdown = max(max_drawdown, drawdown)

    # Max consecutive losses
    max_consec_losses = 0
    current_streak = 0

    for t in closed:
        if t["result"] == "LOSS":
            current_streak += 1
            max_consec_losses = max(max_consec_losses, current_streak)
        else:
            current_streak = 0

    total_return_pct = sum(t["pnl_pct"] for t in closed) * 100

    return {
        "num_trades": n,
        "num_timeouts": len(timeouts),
        "win_rate_pct": round(win_rate * 100, 1),
        "loss_rate_pct": round(loss_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_win_pct": round(avg_win * 100, 2),
        "avg_loss_pct": round(avg_loss * 100, 2),
        "expectancy_pct_per_trade": round(expectancy * 100, 3),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "max_consecutive_losses": max_consec_losses,
        "total_return_pct": round(total_return_pct, 2),
    }


# ==========================================
# MAIN ORCHESTRATION
# ==========================================

def prepare_symbol_data(symbol, now_ms):
    """
    Downloads and pre-sorts 15m/1h/4h history for one symbol,
    including warmup periods before the actual test window.

    Checks the local cache first for each timeframe -- if a
    previous run already downloaded it, we skip re-downloading.
    This means a crash partway through a multi-symbol run only
    costs you the ONE symbol that was downloading when it broke,
    not every symbol before it.

    CAVEAT: the cache doesn't know about LOOKBACK_DAYS or
    END_OFFSET_DAYS changing. If you change either setting,
    delete the historical_data folder first so old cached data
    from a different window isn't silently reused.
    """

    start_15m = now_ms - ms(LOOKBACK_DAYS + WARMUP_DAYS_15M)
    start_1h = now_ms - ms(LOOKBACK_DAYS + WARMUP_DAYS_1H)
    start_4h = now_ms - ms(LOOKBACK_DAYS + WARMUP_DAYS_4H)

    raw_15m = load_cached_data(symbol, "15")
    if raw_15m is None:
        print(f"  Downloading {symbol} 15m history...")
        raw_15m = get_kline_history(symbol, "15", start_15m, now_ms)
        save_cached_data(symbol, "15", raw_15m)

    raw_1h = load_cached_data(symbol, "60")
    if raw_1h is None:
        print(f"  Downloading {symbol} 1h history...")
        raw_1h = get_kline_history(symbol, "60", start_1h, now_ms)
        save_cached_data(symbol, "60", raw_1h)

    raw_4h = load_cached_data(symbol, "240")
    if raw_4h is None:
        print(f"  Downloading {symbol} 4h history...")
        raw_4h = get_kline_history(symbol, "240", start_4h, now_ms)
        save_cached_data(symbol, "240", raw_4h)

    return {
        "15m": sort_oldest_first(raw_15m),
        "1h": sort_oldest_first(raw_1h),
        "4h": sort_oldest_first(raw_4h),
    }


def get_direction_at(data, index_15m, timestamp):
    """
    Given pre-sorted oldest-first 15m/1h/4h arrays for one symbol,
    builds the analysis at a specific point in time by finding the
    correctly-aligned windows on each timeframe.

    Returns (a15, a1h, a4h) or (None, None, None) if not enough data.
    """

    try:
        w15 = window_ending_at(data["15m"], index_15m)

        # The decision happens when the 15m candle starting at
        # `timestamp` closes. A higher-timeframe candle only counts
        # if it has closed by then: start + length <= decision time.
        decision_ms = timestamp + MS_15M

        idx_1h = find_index_at_or_before(data["1h"], decision_ms - MS_1H)
        idx_4h = find_index_at_or_before(data["4h"], decision_ms - MS_4H)

        if idx_1h == -1 or idx_4h == -1:
            return None, None, None

        w1h = window_ending_at(data["1h"], idx_1h)
        w4h = window_ending_at(data["4h"], idx_4h)

        a15 = analyze_market(w15, "SYMBOL_15M")
        a1h = analyze_market(w1h, "SYMBOL_1H")
        a4h = analyze_market(w4h, "SYMBOL_4H")

        return a15, a1h, a4h

    except ValueError:
        # Not enough candles yet (still in warmup) -- skip this point
        return None, None, None


def build_master_timeline(symbol_data_map, start_ms):
    """
    Union of every symbol's 15m candle timestamps at or after
    start_ms, sorted ascending. This is the shared tick sequence
    the simulation steps through -- one combined scan cycle across
    every symbol at once, the same as the live bot's AutoScanner,
    rather than each symbol getting its own private timeline.
    """
    timestamps = set()

    for data in symbol_data_map.values():
        for row in data["15m"]:
            t = int(row[0])
            if t >= start_ms:
                timestamps.add(t)

    return sorted(timestamps)


def run_backtest():

    now_ms_val = int(time.time() * 1000) - ms(END_OFFSET_DAYS)
    test_start_ms = now_ms_val - ms(LOOKBACK_DAYS)

    print("=" * 70)
    if END_OFFSET_DAYS:
        print(
            f"BACKTEST: {LOOKBACK_DAYS} days ending {END_OFFSET_DAYS} days ago, "
            f"{len(SYMBOLS)} symbols"
        )
    else:
        print(f"BACKTEST: {LOOKBACK_DAYS} days, {len(SYMBOLS)} symbols")
    print(
        "One shared trade selection across ALL symbols per scan tick -- "
        "matches main.py's scan_market(), not each symbol in isolation."
    )
    print("=" * 70)

    # --- BTC direction series (computed once per tick, reused for all symbols) ---
    print("\nPreparing BTC reference data...")
    btc_data = prepare_symbol_data("BTCUSDT", now_ms_val)

    symbol_data = {}
    for symbol in SYMBOLS:
        print(f"\nPreparing {symbol} data...")
        symbol_data[symbol] = prepare_symbol_data(symbol, now_ms_val)

    timeline = build_master_timeline(symbol_data, test_start_ms)

    if not timeline:
        print("\n❌ No usable history in the test window for any symbol.")
        return []

    # Leave room at the end of the timeline so a newly-opened trade has a
    # realistic chance to actually resolve (same spirit as the old
    # per-symbol max_entry_index cutoff, just computed on the shared
    # timeline now).
    max_entry_tick = len(timeline) - 1 - MAX_HOLDING_BARS_15M

    open_trades = {}   # (symbol, direction) -> trade dict
    all_trades = []

    print(
        f"\nSimulating {len(timeline)} scan ticks across "
        f"{len(SYMBOLS)} symbols..."
    )

    for tick_index, ts in enumerate(timeline):

        # ---- 1. Update / close existing open trades first ----
        # This mirrors paper_monitor.py: every open trade is checked on
        # every tick, independently of whether a new signal fires this
        # tick. TP2 is the only take-profit level, matching the fixed
        # live monitor -- TP1/TP3 are never evaluated here.
        for key in list(open_trades.keys()):
            symbol, direction = key
            trade = open_trades[key]
            rows = symbol_data[symbol]["15m"]

            idx = find_index_at_or_before(rows, ts)
            if idx == -1 or int(rows[idx][0]) != ts:
                continue  # this symbol has no candle at this exact tick

            if idx <= trade["entry_index"]:
                continue  # never evaluate the entry candle itself

            bars_held = idx - trade["entry_index"]
            high = float(rows[idx][2])
            low = float(rows[idx][3])

            hit = _hit_stop_or_target(
                direction, high, low, trade["stop_loss"], trade["target"]
            )

            result = None
            pnl_pct = 0.0

            if hit == "stop":
                result = "LOSS"
                pnl_pct = _pnl_pct(direction, trade["entry"], trade["stop_loss"])
            elif hit == "target":
                result = "WIN"
                pnl_pct = _pnl_pct(direction, trade["entry"], trade["target"])
            elif bars_held >= MAX_HOLDING_BARS_15M:
                result = "TIMEOUT"
                pnl_pct = 0.0

            if result is not None:
                all_trades.append({
                    "symbol": symbol,
                    "direction": direction,
                    "score": trade["score"],
                    "entry_time_ms": trade["entry_time_ms"],
                    "entry": trade["entry"],
                    "stop_loss": trade["stop_loss"],
                    "result": result,
                    "pnl_pct": pnl_pct,
                    "bars_held": bars_held,
                })
                print(
                    f"  [{result}] {symbol} {direction} "
                    f"score={trade['score']} pnl={pnl_pct * 100:.2f}% "
                    f"bars_held={bars_held}"
                )
                del open_trades[key]

        # ---- 2. Look for at most ONE new trade this tick ----
        # Same rule as scan_market(): every qualifying symbol this tick
        # is a candidate, highest SCORE wins, and only one new trade is
        # opened per tick regardless of how many symbols qualified.
        if tick_index > max_entry_tick:
            continue  # too close to the end of history to let it resolve

        btc_idx = find_index_at_or_before(btc_data["15m"], ts)
        if btc_idx == -1 or int(btc_data["15m"][btc_idx][0]) != ts:
            btc_direction = "WAIT"
        else:
            btc_a15, btc_a1h, btc_a4h = get_direction_at(btc_data, btc_idx, ts)
            if btc_a15 is None:
                btc_direction = "WAIT"
            elif (
                btc_a15["DIRECTION"] == btc_a1h["DIRECTION"]
                and btc_a1h["DIRECTION"] == btc_a4h["DIRECTION"]
            ):
                btc_direction = btc_a1h["DIRECTION"]
            else:
                btc_direction = "WAIT"

        candidates = []

        for symbol in SYMBOLS:
            rows = symbol_data[symbol]["15m"]
            idx = find_index_at_or_before(rows, ts)
            if idx == -1 or int(rows[idx][0]) != ts:
                continue  # no fresh candle for this symbol right now

            a15, a1h, a4h = get_direction_at(symbol_data[symbol], idx, ts)
            if a15 is None:
                continue

            analysis, reason = evaluate_setup(a15, a1h, a4h, btc_direction)
            if analysis is None:
                continue

            # Same explicit gate scan_market() applies on top of
            # evaluate_setup()'s own internal scoring filter.
            if analysis["SCORE"] < config.MIN_SCORE:
                continue

            direction = analysis["DIRECTION"]
            if (symbol, direction) in open_trades:
                continue  # duplicate guard, same as has_open_trade() live

            candidates.append((symbol, idx, analysis))

        if not candidates:
            continue

        # Highest score first; stable sort keeps SYMBOLS list order as
        # the tiebreak -- the same rule scan_market() uses.
        candidates.sort(key=lambda c: c[2]["SCORE"], reverse=True)

        symbol, idx, analysis = candidates[0]
        direction = analysis["DIRECTION"]

        open_trades[(symbol, direction)] = {
            "entry_index": idx,
            "entry_time_ms": ts,
            "entry": analysis["ENTRY"],
            "stop_loss": analysis["STOP_LOSS"],
            "target": analysis["TAKE_PROFIT_2"],
            "score": analysis["SCORE"],
        }

    # Anything still open when history runs out is an unresolved TIMEOUT,
    # not a WIN or LOSS -- we simply ran out of data to know what
    # happened next, same treatment as an in-run timeout.
    for (symbol, direction), trade in open_trades.items():
        all_trades.append({
            "symbol": symbol,
            "direction": direction,
            "score": trade["score"],
            "entry_time_ms": trade["entry_time_ms"],
            "entry": trade["entry"],
            "stop_loss": trade["stop_loss"],
            "result": "TIMEOUT",
            "pnl_pct": 0.0,
            "bars_held": 0,
        })

    print(
        f"\nSimulated {len(timeline)} ticks, found {len(all_trades)} "
        f"trades total."
    )

    from report_extension import print_full_report

    print_full_report(all_trades)

    return all_trades


if __name__ == "__main__":
    run_backtest()