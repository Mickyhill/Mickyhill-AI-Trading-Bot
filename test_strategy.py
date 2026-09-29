from strategy import evaluate_setup

a15 = {
    "DIRECTION": "BUY",
}

a1h = {
    "DIRECTION": "BUY",
    "PRICE": 100,
    "RESISTANCE": 120,
    "SUPPORT": 80,
    "ADX": 35,
    "RSI": 60,
    "MACD": 2,
    "MACD_SIGNAL": 1,
    "VOLUME": 1200,
    "AVG_VOLUME": 1000,
    "RR": 3,
    "EMA20": 105,
    "EMA50": 100,
}

a4h = {
    "DIRECTION": "BUY",
}

analysis, reason = evaluate_setup(
    a15,
    a1h,
    a4h,
    "BUY"
)

if analysis is None:
    print("❌ STRATEGY TEST FAILED")
    print("Reason:", reason)
else:
    print("✅ STRATEGY TEST PASSED")
    print("Direction:", analysis["DIRECTION"])
    print("Score:", analysis["SCORE"])