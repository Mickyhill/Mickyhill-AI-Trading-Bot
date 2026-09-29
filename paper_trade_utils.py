# ==========================================
# MickyHill AI Trading Bot
# paper_trade_utils.py
#
# Step 6F-6G: paper-trade accounting and logging.
# Keeps paper P&L based on position size, includes
# round-trip fees, and writes one final row per closed trade.
# ==========================================

import csv
import os
from datetime import datetime


TRADE_LOG_FILE = "trade_log.csv"


def calculate_paper_pnl(trade, exit_price, round_trip_fee_rate=0.0012):
    """
    Calculate realistic paper-trade P&L.

    The configured fee is a round-trip rate on notional. We split it
    equally between entry and exit so the reported net result includes
    both sides of the simulated trade.

    Returns gross/net P&L in USDT and percentages, fees, and R multiple
    when a valid risk amount is available.
    """
    entry = float(trade["entry"])
    exit_price = float(exit_price)
    direction = trade["direction"]

    sizing = trade.get("sizing") or {}
    quantity = sizing.get("position_size_units")

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        quantity = None

    # Price return is still useful for old paper trades that predate sizing.
    if direction == "BUY":
        gross_pct = (exit_price - entry) / entry
    elif direction == "SELL":
        gross_pct = (entry - exit_price) / entry
    else:
        raise ValueError(f"Unknown trade direction: {direction}")

    # Fee normalized to entry notional. The round-trip rate is split
    # between entry and exit; exit notional changes with the price.
    fee_pct_of_entry_notional = (
        round_trip_fee_rate / 2
        + (round_trip_fee_rate / 2) * (exit_price / entry)
    )
    net_pct = gross_pct - fee_pct_of_entry_notional

    result = {
        "gross_pnl_pct": gross_pct,
        "net_pnl_pct": net_pct,
        "fee_rate_round_trip": round_trip_fee_rate,
        "fee_pct_of_entry_notional": fee_pct_of_entry_notional,
        "fees_usdt": None,
        "gross_pnl_usdt": None,
        "net_pnl_usdt": None,
        "r_multiple": None,
    }

    if quantity is not None and quantity > 0:
        entry_notional = entry * quantity
        exit_notional = exit_price * quantity

        entry_fee = entry_notional * (round_trip_fee_rate / 2)
        exit_fee = exit_notional * (round_trip_fee_rate / 2)
        fees = entry_fee + exit_fee

        if direction == "BUY":
            gross_pnl = (exit_price - entry) * quantity
        else:
            gross_pnl = (entry - exit_price) * quantity

        net_pnl = gross_pnl - fees

        result["fees_usdt"] = fees
        result["gross_pnl_usdt"] = gross_pnl
        result["net_pnl_usdt"] = net_pnl

        risk_amount = sizing.get("risk_amount_usdt")
        try:
            risk_amount = float(risk_amount)
        except (TypeError, ValueError):
            risk_amount = None

        if risk_amount is not None and risk_amount > 0:
            result["r_multiple"] = net_pnl / risk_amount

    return result


def log_closed_trade(trade):
    """Append one final closed-trade record to trade_log.csv."""
    file_exists = os.path.exists(TRADE_LOG_FILE) and os.path.getsize(TRADE_LOG_FILE) > 0

    fieldnames = [
        "closed_at",
        "symbol",
        "direction",
        "score",
        "entry",
        "exit_price",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "take_profit_3",
        "result",
        "gross_pnl_pct",
        "net_pnl_pct",
        "gross_pnl_usdt",
        "fees_usdt",
        "net_pnl_usdt",
        "r_multiple",
        "risk_amount_usdt",
        "position_size_units",
    ]

    row = {field: trade.get(field) for field in fieldnames}
    row["closed_at"] = datetime.fromtimestamp(
        int(trade["closed_timestamp"])
    ).strftime("%Y-%m-%d %H:%M:%S")

    sizing = trade.get("sizing") or {}
    row["risk_amount_usdt"] = sizing.get("risk_amount_usdt")
    row["position_size_units"] = sizing.get("position_size_units")

    with open(TRADE_LOG_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
