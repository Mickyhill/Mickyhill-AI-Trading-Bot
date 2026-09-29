from bybit_api import get_all_symbols, get_kline
from analyzer import analyze_market


def scan_market():

    print("\nScanning market...\n")

    symbols = get_all_symbols()

    opportunities = []

    for symbol in symbols:

        try:

            kline = get_kline(symbol)

            analysis = analyze_market(kline)

            score = 0

            if analysis["EMA20"] > analysis["EMA50"]:
                score += 30

            if analysis["MACD"] > analysis["MACD_SIGNAL"]:
                score += 30

            if analysis["RSI"] > 55:
                score += 20

            if analysis["RSI"] < 70:
                score += 20

            if score >= 70:

                opportunities.append({

                    "symbol": symbol,
                    "score": score,
                    "price": analysis["close"],
                    "analysis": analysis

                })

                print(f"{symbol}  Score: {score}")

        except Exception:
            continue

    opportunities.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return opportunities