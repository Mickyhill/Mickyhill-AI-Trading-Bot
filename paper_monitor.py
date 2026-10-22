# ==========================================
# MickyHill AI Trading Bot
# paper_monitor.py
# Live paper-trade monitoring backed by SQLite.
# ==========================================

import threading
import time

from bybit_api import get_current_price
from notifier import send_message
from paper_db import (
    get_open_trades,
    update_current_price,
    mark_target_hit,
    close_trade,
)
# update_stop_loss (breakeven-after-TP1) is intentionally unused for now —
# see the note on _process_targets below. paper_db.update_stop_loss is
# still there to reintroduce this once there's evidence it's worth the
# added execution complexity.
from paper_trade_utils import calculate_paper_pnl, log_closed_trade
from config import PAPER_ROUND_TRIP_FEE_RATE


class PaperTradeMonitor(threading.Thread):
    def __init__(self, interval_seconds=15):
        super().__init__(daemon=True, name="paper-trade-monitor")
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    @staticmethod
    def _target_reached(direction, price, target):
        return price >= target if direction == "BUY" else price <= target

    @staticmethod
    def _stop_reached(direction, price, stop):
        return price <= stop if direction == "BUY" else price >= stop

    @staticmethod
    def _targets_hit(trade):
        """Return persisted target names already hit for this trade."""
        value = trade.get("targets_hit", [])
        if isinstance(value, str):
            return {x.strip() for x in value.split(",") if x.strip()}
        return set(value or [])

    def _notify_target(self, trade, target, price, status="OPEN"):
        targets = sorted(
            self._targets_hit(trade) | {target},
            key=lambda x: ("TP1", "TP2", "TP3").index(x)
            if x in ("TP1", "TP2", "TP3")
            else 99,
        )
        hit = ", ".join(targets)

        message = f"""
🎯 {trade['symbol']} UPDATE

Direction: {trade['direction']}
Entry: {trade['entry']}

✅ {target} HIT: {price}

TP1: {trade['take_profit_1']}
TP2: {trade['take_profit_2']}
TP3: {trade['take_profit_3']}
SL: {trade['stop_loss']}

Targets Hit: {hit}
Status: {status}
"""
        send_message(message)

    def _notify_close(self, trade, result):
        # TP2 is terminal now (see _process_targets) — matches the single
        # take-profit level order_builder.py actually attaches to a real
        # order, and what backtester.py has always tested against.
        win = result == "TP2"
        icon = "🏁" if win else "🛑"
        result_text = "TP2 HIT" if win else "SL HIT"

        net_pct = trade.get("net_pnl_pct")
        net_usdt = trade.get("net_pnl_usdt")
        fees = trade.get("fees_usdt")
        r_multiple = trade.get("r_multiple")

        net_pct_text = f"{float(net_pct) * 100:.2f}%" if net_pct is not None else "N/A"
        net_usdt_text = f"{float(net_usdt):.6f}" if net_usdt is not None else "N/A"
        fees_text = f"{float(fees):.6f}" if fees is not None else "N/A"
        r_text = f"{float(r_multiple):.2f}" if r_multiple is not None else "N/A"

        message = f"""
{icon} {trade['symbol']} CLOSED

Direction: {trade['direction']}

{'✅' if win else '❌'} {result_text}
Result: {'WIN' if win else 'LOSS'}

Entry: {trade['entry']}
Exit: {trade.get('exit_price', 'N/A')}

Net P&L: {net_pct_text}
Net P&L USDT: {net_usdt_text}
Fees: {fees_text}
R Multiple: {r_text}

Status: CLOSED
"""
        send_message(message)

    def _log_closed(self, trade):
        try:
            log_closed_trade(trade)
        except Exception as exc:
            print(f"⚠️ Could not write trade_log.csv row for {trade.get('trade_id')}: {exc}")

    def _close_at_stop(self, trade, price):
        price = float(trade["stop_loss"])
        accounting = calculate_paper_pnl(
            trade, price, PAPER_ROUND_TRIP_FEE_RATE
        )
        closed = close_trade(
            trade["trade_id"],
            "STOP_LOSS",
            int(time.time()),
            price,
            accounting,
        )
        if not closed:
            return False

        trade["exit_price"] = price
        trade.update(accounting)
        trade["status"] = "CLOSED"
        trade["result"] = "STOP_LOSS"
        trade["closed_timestamp"] = int(time.time())
        self._notify_close(trade, "STOP_LOSS")
        self._log_closed(trade)
        return True

    def _process_targets(self, trade, price):
        """
        Process targets in order. A single live price snapshot may have
        crossed several targets; record each crossed target once.

        TP2 is terminal and closes the trade — this intentionally matches
        the single stop-loss / single take-profit level a real order can
        actually carry today (order_builder.py builds every order against
        TP2, never TP1 or TP3), and what backtester.py has always tested.
        TP1 is recorded and notified as an informational checkpoint only;
        it no longer moves the stop to breakeven. TP3 is not evaluated at
        all — nothing today attaches it to any order, live or paper.
        Riding to TP3 with a breakeven stop after TP1 is a reasonable
        future enhancement, but it needs real partial-close/stop-
        modification support in order execution first, and evidence it
        actually improves on TP2-only before it's worth that complexity.
        """
        hit_targets = self._targets_hit(trade)
        direction = trade["direction"]

        for target_name in ("TP1", "TP2"):
            if target_name in hit_targets:
                continue

            target_price = float(trade[f"take_profit_{target_name[-1]}"])
            if not self._target_reached(direction, price, target_price):
                # Targets are ordered, so a later target cannot be reached if
                # this one has not been reached in the same price snapshot.
                break

            # The DB is the authoritative duplicate-event guard. Only notify
            # when this call successfully records the new event.
            recorded = mark_target_hit(
                trade["trade_id"],
                target_name,
                int(time.time()),
                price,
            )
            if not recorded:
                hit_targets.add(target_name)
                continue

            hit_targets.add(target_name)
            trade["targets_hit"] = list(hit_targets)

            if target_name == "TP2":
                price = target_price
                accounting = calculate_paper_pnl(
                    trade, price, PAPER_ROUND_TRIP_FEE_RATE
                )
                closed = close_trade(
                    trade["trade_id"],
                    "TP2",
                    int(time.time()),
                    price,
                    accounting,
                )
                if closed:
                    trade["exit_price"] = price
                    trade.update(accounting)
                    trade["status"] = "CLOSED"
                    trade["result"] = "TP2"
                    trade["closed_timestamp"] = int(time.time())
                    # TP2 is the terminal event. Send only the final CLOSED
                    # notification; do not first send an OPEN update.
                    self._notify_close(trade, "TP2")
                    self._log_closed(trade)
                return True

            # TP1 remains open and gets a single informational notification.
            self._notify_target(trade, target_name, price, status="OPEN")

        return False

    def check_once(self):
        for trade in get_open_trades():
            try:
                symbol = trade["symbol"]
                price = get_current_price(symbol)
                if price is None:
                    continue
                price = float(price)

                update_current_price(trade["trade_id"], price)

                direction = trade["direction"]
                stop = float(trade["stop_loss"])

                # If the current ticker is at/through SL, close as SL first.
                # With ticker snapshots we cannot know the intrapoll ordering
                # if both SL and TP were crossed. Conservative treatment is SL.
                if self._stop_reached(direction, price, stop):
                    self._close_at_stop(trade, price)
                    continue

                # A trade can cross TP1 and TP2 between polls. Process the
                # ordered targets once; TP2 is terminal and closes the trade.
                self._process_targets(trade, price)

            except Exception as exc:
                print(f"⚠️ Paper monitor error for {trade.get('symbol')}: {exc}")

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.check_once()
            except Exception as exc:
                print(f"⚠️ Paper monitor cycle error: {exc}")

            self.stop_event.wait(self.interval_seconds)