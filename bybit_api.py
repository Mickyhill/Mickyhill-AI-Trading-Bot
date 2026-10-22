# ==========================================
# MickyHill AI Trading Bot
# bybit_api.py
#
# Single Bybit API connection layer.
# ==========================================

import time

from pybit.unified_trading import HTTP
import config
from retry_helper import retry_on_network_error


# ==========================================
# BYBIT SESSION
# ==========================================

session = HTTP(
    testnet=False,
    api_key=config.BYBIT_API_KEY,
    api_secret=config.BYBIT_API_SECRET,
)


# ==========================================
# GET SERVER TIME
# ==========================================

def get_server_time():
    response = retry_on_network_error(session.get_server_time)
    return response


# ==========================================
# GET WALLET BALANCE
# ==========================================

def get_wallet_balance():
    response = retry_on_network_error(
        session.get_wallet_balance,
        accountType="UNIFIED",
        coin="USDT",
    )

    return response


# ==========================================
# GET OPEN POSITIONS
# ==========================================

def get_positions():
    response = retry_on_network_error(
        session.get_positions,
        category="linear",
        settleCoin="USDT",
    )

    return response


# ==========================================
# GET ALL USDT PERPETUAL SYMBOLS
# ==========================================

def get_all_symbols(limit=None):

    response = session.get_instruments_info(
        category="linear",
        limit=1000,
    )

    rows = (
        response
        .get("result", {})
        .get("list", [])
    )

    symbols = []

    for item in rows:

        symbol = item.get("symbol", "")
        status = item.get("status", "")
        quote_coin = item.get("quoteCoin", "")
        contract_type = item.get("contractType", "")

        # ------------------------------------------
        # Basic contract requirements
        # ------------------------------------------

        if not symbol.endswith("USDT"):
            continue

        if quote_coin != "USDT":
            continue

        if status != "Trading":
            continue

        if contract_type != "LinearPerpetual":
            continue

        # ------------------------------------------
        # Exclude tokenized stocks (see config.py —
        # this strategy has never been backtested
        # against this asset class)
        # ------------------------------------------

        root_symbol = symbol[:-4]  # strip trailing "USDT"

        if root_symbol in config.EXCLUDED_STOCK_PROXY_SYMBOLS:
            continue

        symbols.append(symbol)

    # ------------------------------------------
    # Remove duplicates and sort
    # ------------------------------------------

    symbols = sorted(set(symbols))

    # ------------------------------------------
    # Return requested number, or everything
    # ------------------------------------------

    if limit is None:
        return symbols

    return symbols[:limit]


# ==========================================
# CANDLE LENGTHS
#
# Candle length in milliseconds, keyed by
# Bybit's interval code. Used by get_kline()
# to detect the still-forming candle.
# ==========================================

INTERVAL_MS = {
    "1": 60_000,
    "3": 180_000,
    "5": 300_000,
    "15": 900_000,
    "30": 1_800_000,
    "60": 3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "D": 86_400_000,
}


# ==========================================
# GET KLINE
#
# IMPORTANT: returns candles in Bybit's NATIVE
# order (newest-first). Do NOT reverse here —
# analyzer.py's _extract_kline_data() expects
# newest-first input and reverses it internally.
# Reversing in both places double-reverses the
# data and silently corrupts every indicator.
#
# CLOSED CANDLES ONLY: Bybit always puts the
# current, still-forming candle first. That
# candle has partial volume and an unfinished
# close, which made the live volume filter
# reject almost everything and pushed every
# indicator away from what the backtest saw.
# get_kline() drops the forming candle, so live
# scanning only sees closed candles.
# ==========================================

def get_kline(symbol, interval, limit=250):

    response = retry_on_network_error(
        session.get_kline,
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit,
    )

    rows = (
        response
        .get("result", {})
        .get("list", [])
    )

    step = INTERVAL_MS.get(str(interval))

    if step is None:
        print(
            f"⚠️ get_kline: unknown interval {interval}, "
            f"forming candle NOT removed"
        )

    elif rows:
        now_ms = int(time.time() * 1000)

        # rows[0] is the newest candle. If its period
        # hasn't finished yet, drop the candle.
        if int(rows[0][0]) + step > now_ms:
            rows = rows[1:]

    return rows


# ==========================================
# GET CURRENT MARKET PRICE
# ==========================================

def get_current_price(symbol):

    response = retry_on_network_error(
        session.get_tickers,
        category="linear",
        symbol=symbol,
    )

    rows = (
        response
        .get("result", {})
        .get("list", [])
    )

    if not rows:
        return None

    last_price = rows[0].get("lastPrice")

    if last_price is None:
        return None

    return float(last_price)


# ==========================================
# GET HISTORICAL KLINES (PAGINATED)
#
# Used only by backtester.py. Unlike get_kline(),
# this ALWAYS returns oldest-first — backtester.py
# is built to expect that and re-reverses windows
# itself before calling analyze_market(). This
# function's ordering is independent of get_kline()
# above; changing one does not affect the other.
# ==========================================

def get_kline_history(symbol, interval, start_ms, end_ms):
    """
    Fetch all candles between start_ms and end_ms.

    Returns:
        [startTime, open, high, low, close, volume, turnover]

    Oldest candle first.
    """

    all_rows = []
    current_end = end_ms

    while True:

        response = retry_on_network_error(
            session.get_kline,
            category="linear",
            symbol=symbol,
            interval=interval,
            start=start_ms,
            end=current_end,
            limit=1000,
        )

        rows = (
            response
            .get("result", {})
            .get("list", [])
        )

        if not rows:
            break

        all_rows.extend(rows)

        oldest_time = int(rows[-1][0])

        if oldest_time <= start_ms:
            break

        current_end = oldest_time - 1

    # ------------------------------------------
    # Remove duplicate candles
    # ------------------------------------------

    seen = set()
    unique_rows = []

    for row in all_rows:

        timestamp = row[0]

        if timestamp in seen:
            continue

        seen.add(timestamp)
        unique_rows.append(row)

    # ------------------------------------------
    # Oldest first
    # ------------------------------------------

    unique_rows.sort(key=lambda row: int(row[0]))

    return unique_rows


# ==========================================
# GET SYMBOL INFO
# ==========================================

def get_symbol_info(symbol):

    response = session.get_instruments_info(
        category="linear",
        symbol=symbol,
    )

    rows = (
        response
        .get("result", {})
        .get("list", [])
    )

    if not rows:
        return None

    return rows[0]


# ==========================================
# GET TICKER INFORMATION
# ==========================================

def get_ticker(symbol):

    response = session.get_tickers(
        category="linear",
        symbol=symbol,
    )

    rows = (
        response
        .get("result", {})
        .get("list", [])
    )

    if not rows:
        return None

    return rows[0]