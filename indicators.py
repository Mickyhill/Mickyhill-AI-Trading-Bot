import pandas as pd

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands


def prepare_dataframe(kline):

    candles = kline["result"]["list"]

    df = pd.DataFrame(
        candles,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
        ],
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
    ]

    df[numeric_columns] = df[numeric_columns].astype(float)

    df = df.sort_values("time")

    return df


def calculate_indicators(df):

    df["EMA20"] = EMAIndicator(
        close=df["close"],
        window=20,
    ).ema_indicator()

    df["EMA50"] = EMAIndicator(
        close=df["close"],
        window=50,
    ).ema_indicator()

    df["RSI"] = RSIIndicator(
        close=df["close"],
        window=14,
    ).rsi()

    macd = MACD(df["close"])

    df["MACD"] = macd.macd()

    df["MACD_SIGNAL"] = macd.macd_signal()

    bb = BollingerBands(df["close"])

    df["BB_UPPER"] = bb.bollinger_hband()

    df["BB_LOWER"] = bb.bollinger_lband()

    return df