def calculate_score(analysis):

    score = 0

    # ==========================
    # EMA TREND (20)
    # ==========================

    if analysis["EMA20"] > analysis["EMA50"]:
        score += 20

    # ==========================
    # RSI (15)
    # ==========================

    if 55 <= analysis["RSI"] <= 70:
        score += 15

    # ==========================
    # MACD (20)
    # ==========================

    if (
        analysis["MACD"] > analysis["MACD_SIGNAL"]
        and analysis["MACD"] > 0
    ):
        score += 20

    # ==========================
    # VOLUME (15)
    # ==========================

    if analysis["volume"] > analysis["VOLUME_SMA20"] * 1.5:
        score += 15

    # ==========================
    # ADX (20)
    # ==========================

    if analysis["ADX"] > 25:
        score += 20

    # ==========================
    # ATR (10)
    # ==========================

    if analysis["ATR"] > 0:
        score += 10

    return score