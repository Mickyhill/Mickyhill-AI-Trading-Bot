# ==========================================
# MickyHill AI Trading Bot
# main.py
#
# Telegram-controlled paper-trading runner.
# Existing architecture preserved:
# Bybit -> analyzer -> strategy -> risk -> SQLite -> monitor -> Telegram
#
# Important fixes:
# 1. Telegram is the primary scan trigger.
# 2. No second automatic scan loop is started in main.py.
# 3. Only one scan can run at a time.
# 4. A symbol/direction cannot create another paper trade while one is open.
# 5. insert_trade() returning None is handled safely.
# 6. A process-local duplicate guard adds a second layer of protection.
# 7. Signal notification is sent only after a trade is successfully recorded.
# ==========================================

import sys
import time
import threading

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import BOT_NAME, MIN_SCORE, PAPER_TRADE, LIVE_TRADING
from notifier import send_message
from bybit_api import get_server_time, get_wallet_balance, get_positions, get_all_symbols, get_kline
from analyzer import analyze_market
from strategy import evaluate_setup
from risk_manager import get_account_balance_usdt, calculate_position_size
from order_builder import build_order_preview
from circuit_breaker import check_circuit_breaker
from paper_db import init_db, insert_trade, has_open_trade, get_all_trades, get_state
from paper_monitor import PaperTradeMonitor
from auto_scanner import AutoScanner
from telegram_controller import TelegramController


# ==========================================
# SAFETY GATE
# ==========================================

if LIVE_TRADING:
    raise SystemExit(
        "LIVE_TRADING=True is blocked. This project is paper-trading only. "
        "Set LIVE_TRADING=False."
    )


# ==========================================
# TESTED SYMBOL UNIVERSE
#
# Live scanning is restricted to ONLY the symbols
# that have actually been backtested (120 days,
# 743 trades, profit factor 1.32) — not every
# symbol Bybit offers. Before this, live paper
# trades were happening on ~19 different coins
# with ZERO backtest evidence behind any of them.
#
# To add a new symbol here, backtest it first.
# That is the whole point of this list existing.
# ==========================================

TESTED_SYMBOLS = [
    # Original 5
    "SOLUSDT",
    "LINKUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LTCUSDT",

    # Expanded 15-symbol backtest, Aug 2026
    "DOTUSDT",
    "ATOMUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "FILUSDT",
    "INJUSDT",
    "SUIUSDT",
    "ETCUSDT",
]


# ==========================================
# DATABASE / STARTUP
# ==========================================

init_db()

SYMBOLS = TESTED_SYMBOLS


# One scan at a time.
scan_lock = threading.Lock()

# Extra process-level protection. The database remains the persistent source
# of truth; this set prevents accidental repeated creation during one process.
_created_open_keys = set()
_created_open_keys_lock = threading.Lock()


def _trade_key(symbol, direction):
    return f"{str(symbol).upper()}::{str(direction).upper()}"


def _remember_existing_open_trades():
    """Load currently-open DB trades into the process-local guard."""
    try:
        for trade in get_all_trades():
            if trade.get("status") == "OPEN":
                symbol = trade.get("symbol")
                direction = trade.get("direction")
                if symbol and direction:
                    _created_open_keys.add(_trade_key(symbol, direction))
    except Exception as exc:
        print(f"⚠️ Could not preload open-trade guard: {exc}")


def _format_signal_message(best_trade, sizing, trade_recorded=True):
    if "error" in sizing:
        sizing_block = f"Position Size:\nUnavailable ({sizing['error']})"
    else:
        warning_line = (
            f"\n\n⚠️ {sizing['warning']}" if sizing.get("warning") else ""
        )
        sizing_block = f"""Account Balance:
${sizing['account_balance_usdt']}

Risk on This Trade:
${sizing['risk_amount_usdt']} ({sizing['risk_pct_used']}%)

Position Size:
{sizing['position_size_units']:.4f} units (${sizing['position_value_usdt']})

Required Leverage:
{sizing['required_leverage']}x{warning_line}"""

    return f"""
🚀 {BOT_NAME}

━━━━━━━━━━━━━━━━━━━━━━

🏆 ELITE TRADE SIGNAL

━━━━━━━━━━━━━━━━━━━━━━

Coin:
{best_trade['SYMBOL']}

Direction:
{best_trade['DIRECTION']}

Confidence:
{best_trade['SCORE']}/100

━━━━━━━━━━━━━━━━━━━━━━

Current Price:
{best_trade['PRICE']}

Entry Zone:
{best_trade['ENTRY_LOW']}
to
{best_trade['ENTRY_HIGH']}

Suggested Entry:
{best_trade['ENTRY']}

━━━━━━━━━━━━━━━━━━━━━━

Stop Loss:
{best_trade['STOP_LOSS']}

Take Profit 1:
{best_trade['TAKE_PROFIT_1']}

Take Profit 2:
{best_trade['TAKE_PROFIT_2']}

Take Profit 3:
{best_trade['TAKE_PROFIT_3']}

━━━━━━━━━━━━━━━━━━━━━━

Risk / Reward:
1 : {best_trade['RR']}

Suggested Leverage:
{best_trade['LEVERAGE']}x

━━━━━━━━━━━━━━━━━━━━━━

{sizing_block}

━━━━━━━━━━━━━━━━━━━━━━

Trend:
{best_trade['TREND']}

RSI:
{best_trade['RSI']}

MACD:
{best_trade['MACD']}

MACD Signal:
{best_trade['MACD_SIGNAL']}

ADX:
{best_trade['ADX']}

ATR:
{best_trade['ATR']}

Support:
{best_trade['SUPPORT']}

Resistance:
{best_trade['RESISTANCE']}

Volume:
{best_trade['VOLUME']}

Average Volume:
{best_trade['AVG_VOLUME']}

━━━━━━━━━━━━━━━━━━━━━━

{"📝 PAPER TRADE RECORDED" if trade_recorded else "ℹ️ Signal only — PAPER_TRADE is OFF, no trade was recorded"}
"""


def _btc_direction():
    try:
        btc_15m = analyze_market(get_kline("BTCUSDT", "15"), "BTCUSDT")
        btc_1h = analyze_market(get_kline("BTCUSDT", "60"), "BTCUSDT")
        btc_4h = analyze_market(get_kline("BTCUSDT", "240"), "BTCUSDT")

        if btc_15m is None or btc_1h is None or btc_4h is None:
            return "WAIT"

        if (
            btc_15m.get("DIRECTION") == btc_1h.get("DIRECTION")
            and btc_1h.get("DIRECTION") == btc_4h.get("DIRECTION")
        ):
            return btc_1h.get("DIRECTION")

        return "WAIT"
    except Exception as exc:
        print(f"❌ BTC analysis error: {exc}")
        return "WAIT"


def scan_market(notify=True):
    """Run exactly one market scan and optionally create one paper trade."""

    if not scan_lock.acquire(blocking=False):
        message = "⚠️ A market scan is already running. Please wait for it to finish."
        print(message)
        if notify:
            send_message(message)
        return None

    try:
        print("=" * 70)
        print(f"🔎 {BOT_NAME} — MARKET SCAN")
        print("=" * 70)

        btc_direction = _btc_direction()
        print(f"BTC Trend: {btc_direction}")

        symbols = SYMBOLS
        if not symbols:
            # Fall back to the tested list, NEVER to the full unrestricted
            # Bybit universe — that would silently undo the whole point
            # of restricting to backtested symbols.
            print("⚠️ SYMBOLS was empty — falling back to TESTED_SYMBOLS.")
            symbols = TESTED_SYMBOLS

        if not symbols:
            message = "❌ No symbols were available to scan."
            print(message)
            if notify:
                send_message(message)
            return None

        # Collect EVERY qualifying setup this scan, not just the single
        # best one. A scan can have several symbols clear every filter;
        # if we only ever remembered the top scorer, a duplicate-guard
        # hit on that one symbol used to throw away the whole scan even
        # when a second- or third-best candidate was perfectly valid.
        candidates = []

        for index, symbol in enumerate(symbols, start=1):
            print(f"[{index}/{len(symbols)}] {symbol}")
            try:
                k15 = get_kline(symbol, "15")
                k1h = get_kline(symbol, "60")
                k4h = get_kline(symbol, "240")

                a15 = analyze_market(k15, symbol)
                a1h = analyze_market(k1h, symbol)
                a4h = analyze_market(k4h, symbol)

                if a15 is None or a1h is None or a4h is None:
                    continue

                print(
                    f"🔎 {symbol} | "
                    f"15M={a15.get('DIRECTION')} | "
                    f"1H={a1h.get('DIRECTION')} | "
                    f"4H={a4h.get('DIRECTION')}"
                )

                analysis, reason = evaluate_setup(a15, a1h, a4h, btc_direction)
                if analysis is None:
                    print(f"❌ {symbol}: {reason}")
                    continue

                score = analysis["SCORE"]
                print(
                    f"PASSED: {symbol} | {analysis['DIRECTION']} | "
                    f"RR={analysis['RR']:.2f} | Score={score}/100"
                )

                if score >= MIN_SCORE:
                    candidates.append(analysis)

            except Exception as exc:
                print(f"❌ {symbol}: {exc}")

        if not candidates:
            message = "❌ No quality trade setup found in the current market scan."
            print(message)
            if notify:
                send_message(message)
            return None

        # Highest score first; Python's sort is stable, so ties keep
        # scan order (i.e. SYMBOLS list order) as the tiebreak.
        candidates.sort(key=lambda a: a["SCORE"], reverse=True)

        best_trade = None
        skipped_duplicates = []

        for candidate in candidates:
            candidate_symbol = candidate["SYMBOL"]
            candidate_direction = candidate["DIRECTION"]
            candidate_key = _trade_key(candidate_symbol, candidate_direction)

            if has_open_trade(candidate_symbol, candidate_direction):
                skipped_duplicates.append((candidate_symbol, candidate_direction))
                with _created_open_keys_lock:
                    _created_open_keys.add(candidate_key)
                continue

            with _created_open_keys_lock:
                if candidate_key in _created_open_keys:
                    skipped_duplicates.append((candidate_symbol, candidate_direction))
                    continue

            # First candidate, in score order, that isn't a duplicate wins.
            best_trade = candidate
            break

        if best_trade is None:
            skipped_text = ", ".join(f"{s} {d}" for s, d in skipped_duplicates)
            message = (
                f"⏭️ {len(candidates)} qualifying setup(s) this scan, but all "
                f"already have an OPEN paper trade: {skipped_text}\n\n"
                "No new paper trade was created."
            )
            print(message)
            if notify:
                send_message(message)
            return None

        symbol = best_trade["SYMBOL"]
        direction = best_trade["DIRECTION"]
        key = _trade_key(symbol, direction)

        # Both guards below are now redundant in the common case — the
        # candidate loop above already filtered out duplicates — but are
        # kept as defense-in-depth against a trade opening in the brief
        # window between that check and this point.
        if has_open_trade(symbol, direction):
            message = (
                f"⏭️ {symbol} {direction} already has an OPEN paper trade.\n\n"
                "No duplicate paper trade was created."
            )
            print(message)
            with _created_open_keys_lock:
                _created_open_keys.add(key)
            if notify:
                send_message(message)
            return best_trade

        with _created_open_keys_lock:
            if key in _created_open_keys:
                message = (
                    f"⏭️ Duplicate paper trade blocked: {symbol} {direction}\n\n"
                    "An OPEN paper trade for this symbol/direction is already tracked."
                )
                print(message)
                if notify:
                    send_message(message)
                return best_trade

        # Circuit breaker only blocks NEW paper trades. Trades closed at
        # or before the manual reset marker (if one was ever set, e.g.
        # via the Telegram "Reset Circuit Breaker" action) are excluded
        # from the streak calculation, so a manual reset actually clears
        # the streak instead of being immediately recomputed away.
        reset_at = int(get_state("circuit_breaker_reset_at", 0))
        closed_trades = [
            t for t in get_all_trades()
            if t.get("status") == "CLOSED"
            and (t.get("closed_timestamp") or 0) > reset_at
        ]
        breaker = check_circuit_breaker(closed_trades)
        if breaker.get("paused"):
            message = (
                "🛑 CIRCUIT BREAKER ACTIVE\n\n"
                f"Reason: {breaker.get('reason', 'Unknown')}\n"
                "No new paper trade was created."
            )
            print(message)
            if notify:
                send_message(message)
            return best_trade

        account_balance = get_account_balance_usdt()
        sizing = calculate_position_size(
            account_balance_usdt=account_balance,
            entry_price=best_trade["ENTRY"],
            stop_loss_price=best_trade["STOP_LOSS"],
        )

        if "error" not in sizing:
            preview = build_order_preview(
                symbol=symbol,
                direction=direction,
                quantity=sizing["position_size_units"],
                entry_price=best_trade["ENTRY"],
                stop_loss=best_trade["STOP_LOSS"],
                take_profit_2=best_trade["TAKE_PROFIT_2"],
                leverage=sizing["required_leverage"],
            )
            print(
                preview.get("preview_text")
                if preview.get("built")
                else preview.get("errors")
            )
        else:
            print(f"⚠️ Position sizing unavailable: {sizing['error']}")

        if not PAPER_TRADE:
            print("⚠️ PAPER_TRADE is OFF — no paper trade created.")
            if notify:
                send_message(_format_signal_message(best_trade, sizing, trade_recorded=False))
            return best_trade

        now = int(time.time())
        paper_trade = {
            "symbol": symbol,
            "direction": direction,
            "score": best_trade["SCORE"],
            "entry": best_trade["ENTRY"],
            "stop_loss": best_trade["STOP_LOSS"],
            "take_profit_1": best_trade["TAKE_PROFIT_1"],
            "take_profit_2": best_trade["TAKE_PROFIT_2"],
            "take_profit_3": best_trade["TAKE_PROFIT_3"],
            "status": "OPEN",
            "type": "PAPER",
            "timestamp": now,
            "opened_timestamp": now,
            "signal_time": now,
            "targets_hit": [],
            "sizing": sizing,
        }

        # insert_trade() is expected to return None when a duplicate is blocked.
        trade_id = insert_trade(paper_trade)

        if trade_id is None:
            message = (
                f"⏭️ Duplicate paper trade blocked: {symbol} {direction}\n\n"
                "No second database record was created."
            )
            print(message)
            with _created_open_keys_lock:
                _created_open_keys.add(key)
            if notify:
                send_message(message)
            return best_trade

        paper_trade["trade_id"] = trade_id

        with _created_open_keys_lock:
            _created_open_keys.add(key)

        print(f"📝 PAPER TRADE RECORDED: {trade_id}")

        if notify:
            send_message(_format_signal_message(best_trade, sizing))

        return best_trade

    except Exception as exc:
        print(f"❌ Market scan error: {exc}")
        if notify:
            send_message(f"❌ Market scan failed: {exc}")
        return None

    finally:
        scan_lock.release()


def main():
    print(f"🚀 {BOT_NAME}")
    print("🟢 PAPER TRADING: ON" if PAPER_TRADE else "⚪ PAPER TRADING: OFF")
    print("🔴 LIVE TRADING: OFF")
    print(f"🎯 Scanning {len(SYMBOLS)} backtested symbols: {', '.join(SYMBOLS)}")
    print("🗄️ SQLite paper-trade database: ON")
    print("👀 Paper-trade monitor: ON")
    print("🤖 Telegram control: ON")
    print("📱 Automatic market scan loop: ON — every 15 minutes (plus Telegram Scan Market anytime)")

    _remember_existing_open_trades()

    # Optional startup diagnostics. Failures here do not stop the bot.
    try:
        print(f"Server time: {get_server_time()}")
    except Exception as exc:
        print(f"⚠️ Server time unavailable: {exc}")

    try:
        print(f"Wallet: {get_wallet_balance()}")
    except Exception as exc:
        print(f"⚠️ Wallet unavailable: {exc}")

    try:
        print(f"Positions: {get_positions()}")
    except Exception as exc:
        print(f"⚠️ Positions unavailable: {exc}")

    monitor = PaperTradeMonitor(interval_seconds=15)
    telegram = TelegramController(scan_market)
    auto_scanner = AutoScanner(scan_market, interval_seconds=900)

    monitor.start()
    telegram.start()
    auto_scanner.start()

    print("✅ Bot is running. Auto-scanning every 15 minutes, plus Telegram Scan Market anytime.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down MickyHill AI Trading Bot...")
        try:
            telegram.stop()
        except Exception:
            pass
        try:
            monitor.stop()
        except Exception:
            pass
        try:
            auto_scanner.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
