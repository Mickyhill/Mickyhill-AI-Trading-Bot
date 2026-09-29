import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# BOT
# ==========================================

BOT_NAME = "MickyHill AI Trading Bot"

# ==========================================
# BYBIT
# ==========================================

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

# ==========================================
# TELEGRAM
# ==========================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==========================================
# TRADING SETTINGS
# ==========================================

CATEGORY = "linear"

TIMEFRAME_15M = "15"
TIMEFRAME_1H = "60"
TIMEFRAME_4H = "240"

SCAN_LIMIT = 100

# ==========================================
# FILTERS
# ==========================================

MIN_VOLUME_24H = 5_000_000

MIN_PRICE = 0.00001

MIN_ADX = 18

MIN_RR = 1.5

BUY_RSI_LIMIT = 80

SELL_RSI_LIMIT = 20

# ==========================================
# SCORING
# ==========================================

MIN_SCORE = 80

MAX_SCORE = 100

# ==========================================
# EXECUTION MODE
#
# These are two SEPARATE switches on purpose —
# never merge them into one flag. PAPER_TRADE
# controls whether the bot records simulated
# trades. LIVE_TRADING controls whether it is
# even ALLOWED to attempt a real order.
#
# LIVE_TRADING must stay False until Step 6D-F
# (order construction, validation, and the hard
# execution gate) are built and verified. main.py
# refuses to start at all if this is True before
# that work exists — see the startup check there.
# ==========================================

PAPER_TRADE = True
LIVE_TRADING = False

# ==========================================
# RISK
# ==========================================

DEFAULT_LEVERAGE = 10

RISK_PER_TRADE = 0.01

# Estimated total paper-trade fee for entry + exit.
# Used only for paper accounting; it does not send any orders.
PAPER_ROUND_TRIP_FEE_RATE = 0.0012

# ==========================================
# SUPPORT / RESISTANCE BUFFER
# ==========================================

RESISTANCE_BUFFER = 0.995

SUPPORT_BUFFER = 1.005

# ==========================================
# EXCLUDED SYMBOLS — TOKENIZED STOCKS
#
# Bybit lists tokenized-stock perpetuals (Apple,
# Nvidia, Take-Two, etc.) alongside real crypto,
# with NO distinguishing field in the API to tell
# them apart — only the ticker name. This list is
# maintained BY HAND and is not guaranteed
# complete; Bybit adds new ones periodically.
#
# Excluded because the strategy's backtest (120
# days, SOL/LINK/ADA/AVAX/LTC) has never been
# tested against this asset class, which can
# trade very differently (different liquidity
# hours, different volatility character) than
# native crypto.
#
# If you notice a new one slipping through
# (anything that's clearly a stock ticker, not a
# coin), add its root symbol here.
# ==========================================

EXCLUDED_STOCK_PROXY_SYMBOLS = {
    "AAPL", "ABNB", "ADBE", "AMD", "AMDSTOCK", "AMZN", "APPSTOCK",
    "ASML", "AVGO", "BABA", "BAC", "COIN", "COST", "CRM", "DIS",
    "GOOGL", "GS", "INTC", "JNJ", "JPM", "KO", "MA", "MCD", "META",
    "MSFT", "MSTR", "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE",
    "PG", "PYPL", "QCOM", "SBUX", "TSLA", "TSM", "TTWO", "UNH",
    "V", "WMT", "XOM",
}