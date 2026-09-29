# ==========================================
# MickyHill AI Trading Bot
# analyzer.py
# ==========================================

import math


# ==========================================
# BASIC HELPERS
# ==========================================

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_kline_data(kline_response):
    """
    Converts Bybit kline response into candle arrays.

    Bybit returns:
    [startTime, open, high, low, close, volume, turnover]
    """

    if not kline_response:
        raise ValueError("Empty kline response")

    if isinstance(kline_response, dict):
        rows = kline_response.get("result", {}).get("list", [])
    else:
        rows = kline_response

    if not rows:
        raise ValueError("No kline data found")

    # Bybit returns newest candle first.
    rows = list(reversed(rows))

    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []

    for row in rows:
        if len(row) < 6:
            continue

        opens.append(_safe_float(row[1]))
        highs.append(_safe_float(row[2]))
        lows.append(_safe_float(row[3]))
        closes.append(_safe_float(row[4]))
        volumes.append(_safe_float(row[5]))

    if len(closes) < 60:
        raise ValueError(
            f"Not enough candles. Received {len(closes)}, need at least 60."
        )

    return opens, highs, lows, closes, volumes


# ==========================================
# EMA
# ==========================================

def _ema(values, period):
    if len(values) < period:
        raise ValueError(f"Not enough data for EMA{period}")

    multiplier = 2 / (period + 1)

    ema_value = sum(values[:period]) / period

    result = [ema_value]

    for price in values[period:]:
        ema_value = (
            price - ema_value
        ) * multiplier + ema_value

        result.append(ema_value)

    return result


# ==========================================
# RSI
# ==========================================

def _rsi(values, period=14):

    if len(values) <= period:
        return 50.0

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# ==========================================
# ATR
# ==========================================

def _atr(highs, lows, closes, period=14):

    if len(closes) <= period:
        return 0.0

    true_ranges = []

    for i in range(1, len(closes)):

        high = highs[i]
        low = lows[i]
        previous_close = closes[i - 1]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return 0.0

    atr_value = sum(true_ranges[:period]) / period

    for tr in true_ranges[period:]:
        atr_value = (
            (atr_value * (period - 1)) + tr
        ) / period

    return atr_value


# ==========================================
# MACD
# ==========================================

def _macd(values):

    ema12 = _ema(values, 12)
    ema26 = _ema(values, 26)

    # Align both arrays.
    macd_values = []

    offset = len(ema12) - len(ema26)

    ema12_aligned = ema12[offset:]

    for fast, slow in zip(
        ema12_aligned,
        ema26
    ):
        macd_values.append(fast - slow)

    if len(macd_values) < 9:
        return 0.0, 0.0, 0.0, 0.0

    signal_values = _ema(macd_values, 9)

    macd_line = macd_values[-1]
    signal_line = signal_values[-1]

    histogram = macd_line - signal_line

    previous_histogram = (
        macd_values[-2] - signal_values[-2]
    )

    return (
        macd_line,
        signal_line,
        histogram,
        previous_histogram
    )


# ==========================================
# ADX
# ==========================================

def _adx(highs, lows, closes, period=14):

    if len(closes) < period * 2:
        return 0.0

    tr_values = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(closes)):

        high = highs[i]
        low = lows[i]

        previous_high = highs[i - 1]
        previous_low = lows[i - 1]
        previous_close = closes[i - 1]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        up_move = high - previous_high
        down_move = previous_low - low

        plus = (
            up_move
            if up_move > down_move and up_move > 0
            else 0
        )

        minus = (
            down_move
            if down_move > up_move and down_move > 0
            else 0
        )

        tr_values.append(tr)
        plus_dm.append(plus)
        minus_dm.append(minus)

    if len(tr_values) < period:
        return 0.0

    atr_value = sum(tr_values[:period]) / period
    plus_value = sum(plus_dm[:period]) / period
    minus_value = sum(minus_dm[:period]) / period

    dx_values = []

    for i in range(period, len(tr_values)):

        atr_value = (
            (atr_value * (period - 1))
            + tr_values[i]
        ) / period

        plus_value = (
            (plus_value * (period - 1))
            + plus_dm[i]
        ) / period

        minus_value = (
            (minus_value * (period - 1))
            + minus_dm[i]
        ) / period

        if atr_value == 0:
            continue

        plus_di = 100 * plus_value / atr_value
        minus_di = 100 * minus_value / atr_value

        denominator = plus_di + minus_di

        if denominator == 0:
            continue

        dx = (
            100
            * abs(plus_di - minus_di)
            / denominator
        )

        dx_values.append(dx)

    if len(dx_values) < period:
        return 0.0

    adx_value = sum(dx_values[:period]) / period

    for dx in dx_values[period:]:
        adx_value = (
            (adx_value * (period - 1)) + dx
        ) / period

    return adx_value


# ==========================================
# SUPPORT
# ==========================================

def _support(lows, lookback=30):

    data = lows[-lookback:]

    if not data:
        return 0.0

    return min(data)


# ==========================================
# RESISTANCE
# ==========================================

def _resistance(highs, lookback=30):

    data = highs[-lookback:]

    if not data:
        return 0.0

    return max(data)


# ==========================================
# AVERAGE VOLUME
# ==========================================

def _average_volume(volumes, period=20):

    if not volumes:
        return 0.0

    data = volumes[-period:]

    return sum(data) / len(data)


# ==========================================
# TREND
# ==========================================

def _get_trend(
    ema20,
    ema50,
    price
):

    if price > ema20 > ema50:
        return "BULLISH"

    if price < ema20 < ema50:
        return "BEARISH"

    return "NEUTRAL"


# ==========================================
# ANALYZE MARKET
# ==========================================

def analyze_market(kline_response, symbol):

    opens, highs, lows, closes, volumes = (
        _extract_kline_data(kline_response)
    )

    price = closes[-1]

    # --------------------------------------
    # EMA
    # --------------------------------------

    ema20_values = _ema(closes, 20)
    ema50_values = _ema(closes, 50)

    ema20 = ema20_values[-1]
    ema50 = ema50_values[-1]

    # --------------------------------------
    # RSI
    # --------------------------------------

    rsi = _rsi(closes, 14)

    # --------------------------------------
    # MACD
    # --------------------------------------

    macd, macd_signal, macd_histogram, previous_macd_histogram = (
    _macd(closes)
)

    # --------------------------------------
    # ATR
    # --------------------------------------

    atr = _atr(
        highs,
        lows,
        closes,
        14
    )

    # --------------------------------------
    # ADX
    # --------------------------------------

    adx = _adx(
        highs,
        lows,
        closes,
        14
    )

    # --------------------------------------
    # VOLUME
    # --------------------------------------

    volume = volumes[-1]

    avg_volume = _average_volume(
        volumes,
        20
    )

    # --------------------------------------
    # SUPPORT / RESISTANCE
    # --------------------------------------

    support = _support(
        lows,
        30
    )

    resistance = _resistance(
        highs,
        30
    )

    # --------------------------------------
    # TREND
    # --------------------------------------

    trend = _get_trend(
        ema20,
        ema50,
        price
    )

    # --------------------------------------
    # DIRECTION
    # --------------------------------------

    bullish_score = 0
    bearish_score = 0

    if price > ema20:
        bullish_score += 1
    else:
        bearish_score += 1

    if ema20 > ema50:
        bullish_score += 1
    else:
        bearish_score += 1

    if macd > macd_signal:
        bullish_score += 1
    else:
        bearish_score += 1

    if rsi > 50:
        bullish_score += 1
    else:
        bearish_score += 1

    if adx >= 18:

        if bullish_score > bearish_score:
            direction = "BUY"

        elif bearish_score > bullish_score:
            direction = "SELL"

        else:
            direction = "WAIT"

    else:
        direction = "WAIT"

    # --------------------------------------
    # ENTRY ZONE
    # --------------------------------------

    if direction == "BUY":

        entry_low = price - (atr * 0.25)
        entry_high = price + (atr * 0.10)

        entry = (
            entry_low + entry_high
        ) / 2

        stop_loss = (
            entry - (atr * 1.5)
        )

        risk = abs(entry - stop_loss)

        take_profit_1 = entry + (risk * 1.5)
        take_profit_2 = entry + (risk * 2.0)
        take_profit_3 = entry + (risk * 3.0)

    elif direction == "SELL":

        entry_low = price - (atr * 0.10)
        entry_high = price + (atr * 0.25)

        entry = (
            entry_low + entry_high
        ) / 2

        stop_loss = (
            entry + (atr * 1.5)
        )

        risk = abs(stop_loss - entry)

        take_profit_1 = entry - (risk * 1.5)
        take_profit_2 = entry - (risk * 2.0)
        take_profit_3 = entry - (risk * 3.0)

    else:

        entry_low = price
        entry_high = price
        entry = price

        stop_loss = price

        take_profit_1 = price
        take_profit_2 = price
        take_profit_3 = price

        risk = 0.0

    # --------------------------------------
    # RISK / REWARD
    # --------------------------------------

    if risk > 0:

        if direction == "BUY":
            reward = abs(
                take_profit_2 - entry
            )

        elif direction == "SELL":
            reward = abs(
                entry - take_profit_2
            )

        else:
            reward = 0.0

        rr = reward / risk

    else:
        rr = 0.0

    # --------------------------------------
    # LEVERAGE
    # --------------------------------------

    if adx >= 35:
        leverage = 5

    elif adx >= 25:
        leverage = 3

    else:
        leverage = 2

    # --------------------------------------
    # RESULT
    # --------------------------------------

    return {
        "SYMBOL": symbol,

        "DIRECTION": direction,

        "PRICE": price,

        "ENTRY_LOW": entry_low,
        "ENTRY_HIGH": entry_high,
        "ENTRY": entry,

        "STOP_LOSS": stop_loss,

        "TAKE_PROFIT_1": take_profit_1,
        "TAKE_PROFIT_2": take_profit_2,
        "TAKE_PROFIT_3": take_profit_3,

        "RR": rr,

        "LEVERAGE": leverage,

        "TREND": trend,

        "RSI": rsi,

        "MACD": macd,
"MACD_SIGNAL": macd_signal,
"MACD_HISTOGRAM": macd_histogram,
"PREVIOUS_MACD_HISTOGRAM": previous_macd_histogram,

        "ADX": adx,

        "ATR": atr,

        "VOLUME": volume,
        "AVG_VOLUME": avg_volume,

        "SUPPORT": support,
        "RESISTANCE": resistance,

        "EMA20": ema20,
        "EMA50": ema50,
    }