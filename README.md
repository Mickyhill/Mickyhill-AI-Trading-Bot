# MickyHill AI Trading Bot

A Python system for crypto market analysis and trade signal generation. The bot reads market data from Bybit, filters trade setups, sets entry, stop-loss and take-profit levels, applies risk controls, and sends each signal to Telegram.

**Stack:** Python, Bybit API, Telegram Bot API, REST APIs.

**Status:** Paper trading and backtesting only. The bot places no live trades.

## Features

- **Market analysis.** Pulls price data from the Bybit API and checks each market against the signal rules.
- **Signal filtering.** Drops weak setups before a signal goes out.
- **Trade levels.** Every signal includes an entry price, a stop-loss and a take-profit.
- **Risk controls.** Limits position size and exposure per trade.
- **Telegram alerts.** Sends each signal to a Telegram chat.
- **Paper trading.** Tracks simulated trades so results get measured before any real money goes in.

## Project structure

```
[FILL IN: list the main files and folders, for example]
main.py            entry point
strategy/          signal and filter logic
risk/              stop-loss, take-profit and position sizing
notifier/          Telegram messages
requirements.txt   Python dependencies
.env.example       template for API keys
```

## Run locally

1. Clone the repo and install dependencies:

```bash
git clone https://github.com/Mickyhill/Mickyhill-AI-Trading-Bot.git
cd Mickyhill-AI-Trading-Bot
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and add your own keys:

```
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

Use Bybit testnet keys with read-only or paper-trading permissions. Never commit the `.env` file.

3. Start the bot:

```bash
python [FILL IN: main file name].py
```

## Disclaimer

This project is for learning and research. Signals are not financial advice. Crypto trading carries a high risk of loss.

## Author

Michael Churchill, Software Engineering student, Federal University of Technology, Ikot Abasi (FUTIA), Nigeria.
Portfolio: [mickyhill.floot.app](https://mickyhill.floot.app)
