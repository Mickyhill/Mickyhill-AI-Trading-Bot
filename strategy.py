# ==========================================
# MickyHill AI Trading Bot
# strategy.py
#
# Single source of truth for "what counts as a
# valid trade setup." Both main.py (live scanning)
# and backtester.py (historical testing) call
# evaluate_setup() so they always agree.
# ==========================================

import config

def evaluate_setup(a15, a1h, a4h, btc_direction):
    """
    Runs the full trade-decision pipeline.

    Returns (analysis, None) if the setup passes
    every filter and gets a score.

    Returns (None, reason) if it gets rejected,
    where reason is a short human-readable string.
    """

    if a15 is None or a1h is None or a4h is None:
        return None, "Invalid analysis"

    # -----------------------------
    # Multi-Timeframe Direction
    # 4H = context, 1H = primary direction, 15M = entry confirmation
    # -----------------------------

    if a1h["DIRECTION"] == "WAIT":
        return None, "No clear 1H direction"

    if (
        a4h["DIRECTION"] != "WAIT"
        and a4h["DIRECTION"] != a1h["DIRECTION"]
    ):
        return None, "4H context conflicts with 1H direction"

    if (
        a15["DIRECTION"] != "WAIT"
        and a15["DIRECTION"] != a1h["DIRECTION"]
    ):
        return None, "15M entry timing conflicts with 1H direction"

    analysis = a1h

    # -----------------------------
    # Bitcoin Filter
    # -----------------------------

    if analysis["DIRECTION"] == "BUY" and btc_direction == "SELL":
        return None, "BTC trend conflict"

    if analysis["DIRECTION"] == "SELL" and btc_direction == "BUY":
        return None, "BTC trend conflict"

    # -----------------------------
    # Support / Resistance Filter
    # -----------------------------

    if (
        analysis["DIRECTION"] == "BUY"
        and analysis["PRICE"] > analysis["RESISTANCE"] * config.RESISTANCE_BUFFER
    ):
        return None, "Too close to resistance"

    if (
        analysis["DIRECTION"] == "SELL"
        and analysis["PRICE"] < analysis["SUPPORT"] * config.SUPPORT_BUFFER
    ):
        return None, "Too close to support"

    # -----------------------------
    # ADX Filter
    # -----------------------------

    if analysis["ADX"] < config.MIN_ADX:
        return None, f"ADX too low ({analysis['ADX']:.2f})"

    # -----------------------------
    # RSI Filter (direction-aware)
    #
    # NOTE: this is a deliberate "sweet spot" range filter, not the
    # same thing as config.BUY_RSI_LIMIT / config.SELL_RSI_LIMIT.
    # Those two constants describe a single-sided overbought/oversold
    # ceiling (e.g. "never BUY above RSI 80"), while this filter
    # requires RSI to sit inside a tighter momentum band before
    # entering at all. The two are not interchangeable — swapping one
    # in for the other would loosen entries, not just rename a
    # number — so BUY_RSI_LIMIT/SELL_RSI_LIMIT are intentionally left
    # unused here rather than silently changing what qualifies as a
    # valid setup. If a hard overbought/oversold ceiling on top of
    # this range is wanted, add it as its own explicit check instead
    # of replacing this one.
    # -----------------------------

    if (
        analysis["DIRECTION"] == "BUY"
        and (analysis["RSI"] < 45 or analysis["RSI"] > 70)
    ):
        return None, f"RSI not suitable for BUY ({analysis['RSI']:.2f})"

    if (
        analysis["DIRECTION"] == "SELL"
        and (analysis["RSI"] > 55 or analysis["RSI"] < 30)
    ):
        return None, f"RSI not suitable for SELL ({analysis['RSI']:.2f})"

    # -----------------------------
    # MACD Filter
    # -----------------------------

    if analysis["MACD"] is None:
        return None, "MACD unavailable"

    if analysis["DIRECTION"] == "BUY" and analysis["MACD"] <= 0:
        return None, f"MACD does not support BUY ({analysis['MACD']:.6f})"

    if analysis["DIRECTION"] == "SELL" and analysis["MACD"] >= 0:
        return None, f"MACD does not support SELL ({analysis['MACD']:.6f})"

    # -----------------------------
    # Volume Filter
    # -----------------------------

    if analysis["VOLUME"] < analysis["AVG_VOLUME"] * 0.70:
        return None, "Volume too low"

    # -----------------------------
    # Risk / Reward
    # -----------------------------

    if analysis["RR"] < config.MIN_RR:
        return None, f"RR too low ({analysis['RR']:.2f})"


    # -----------------------------
    # Calculate Score
    # -----------------------------

    score = 0

    # Trend
    if (
        analysis["DIRECTION"] == "BUY"
        and analysis["EMA20"] > analysis["EMA50"]
    ):
        score += 30
    elif (
        analysis["DIRECTION"] == "SELL"
        and analysis["EMA20"] < analysis["EMA50"]
    ):
        score += 30

    # Momentum
    if (
        analysis["DIRECTION"] == "BUY"
        and analysis["MACD"] > analysis["MACD_SIGNAL"]
    ):
        score += 20
    elif (
        analysis["DIRECTION"] == "SELL"
        and analysis["MACD"] < analysis["MACD_SIGNAL"]
    ):
        score += 20

    # RSI
    if 50 <= analysis["RSI"] <= 65:
        score += 15
    elif 65 < analysis["RSI"] <= 70:
        score += 10

    # ADX
    if analysis["ADX"] >= 35:
        score += 15
    elif analysis["ADX"] >= 25:
        score += 10

    # Volume
    if analysis["VOLUME"] > analysis["AVG_VOLUME"]:
        score += 10

    # Risk / Reward
    if analysis["RR"] >= 3:
        score += 10
    elif analysis["RR"] >= 2:
        score += 5

    score = min(score, 100)
    analysis["SCORE"] = score

    if score < config.MIN_SCORE:
        return None, f"Score too low ({score}/{config.MIN_SCORE})"

    return analysis, None