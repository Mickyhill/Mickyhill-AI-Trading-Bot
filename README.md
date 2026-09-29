# MickyHill AI Trading Bot

A Python system for crypto market analysis and paper trading on Bybit. The bot scans a fixed list of backtested symbols across three timeframes, filters and scores trade setups, sizes positions by risk, records paper trades in SQLite, monitors open trades, and sends signals to Telegram.

**Stack:** Python, Bybit V5 API (pybit), Telegram Bot API, SQLite.

**Status:** Paper trading and backtesting only. Live trading is blocked in code.

## Features

- **Multi-timeframe analysis.** Checks 15-minute, 1-hour and 4-hour candles for each symbol, plus BTC direction as a market filter.
- **Backtested symbol list.** Scans 15 symbols tested in a 120-day backtest. A symbol gets added only after a backtest.
- **Setup scoring.** Each setup gets a score out of 100. Only setups above the minimum score qualify.
- **Trade levels.** Every signal includes an entry zone, a stop-loss and three take-profit targets.
- **Risk management.** Position size comes from account balance and stop-loss distance.
- **Circuit breaker.** Pauses new paper trades after a losing streak, with a manual reset from Telegram.
- **Duplicate protection.** Blocks a second open paper trade on the same symbol and direction.
- **Paper trade monitor.** Tracks open paper trades every 15 seconds and closes them at stop-loss or targets.
- **Telegram control.** Trigger a market scan from Telegram at any time. The bot also scans automatically every 15 minutes.
- **Safety gate.** The bot refuses to start if live trading is switched on.

## Project structure

```
main.py                 entry point: scan loop, Telegram control, paper trade monitor
config.py               settings, loaded from environment variables
bybit_api.py            Bybit market data, wallet and positions
analyzer.py             indicators per timeframe (trend, RSI, MACD, ADX, ATR)
indicators.py           indicator calculations
strategy.py             setup rules across 15m, 1h and 4h
scorer.py               setup scoring
scanner.py              market scanning helpers
auto_scanner.py         automatic scan every 15 minutes
risk_manager.py         position sizing
circuit_breaker.py      losing-streak pause
order_builder.py        order preview
order_validator.py      order checks
paper_db.py             SQLite storage for paper trades
paper_monitor.py        monitors open paper trades
paper_trade_utils.py    paper trade helpers
telegram_controller.py  Telegram commands
notifier.py             Telegram messages
backtester.py           historical backtesting
retry_helper.py         retries for API calls
test_*.py               tests
```

## Run locally

1. Clone the repo and install dependencies:

```bash
git clone https://github.com/Mickyhill/Mickyhill-AI-Trading-Bot.git
cd Mickyhill-AI-Trading-Bot
python -m venv venv
venv\Scripts\activate           # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and add your own values:

```
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

Market data needs no key. The Bybit key only reads wallet balance for position sizing, so use a Read-Only key. Never commit the `.env` file.

3. Start the bot:

```bash
python main.py
```

## Disclaimer

This project is for learning and research. Signals are not financial advice. Crypto trading carries a high risk of loss.

## Author

Michael Churchill, Software Engineering student, Federal University of Technology, Ikot Abasi (FUTIA), Nigeria.
Portfolio: [mickyhill.floot.app](https://mickyhill.floot.app)