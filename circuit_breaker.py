# ==========================================
# MickyHill AI Trading Bot
# circuit_breaker.py
#
# Pauses NEW paper (and eventually real) trades
# after a run of consecutive losses or a bad day,
# without stopping the scanner entirely — existing
# open trades still get monitored and closed
# normally. Nothing here sends or blocks real
# orders (none exist yet); this only controls
# whether main.py records a NEW paper trade.
# ==========================================

import time


def check_circuit_breaker(
    closed_trades,
    max_consecutive_losses=5,
    max_daily_loss_pct=0.05,
    now=None,
):
    """
    closed_trades: list of trade dicts with status == "CLOSED",
                   each having 'result' ("STOP_LOSS" or "TP3"),
                   'pnl_pct', and 'closed_timestamp'.

    Returns a dict:
      paused: True/False
      reason: string explaining why, or None
      consecutive_losses: current streak length
      daily_pnl_pct: net P&L over the last 24 hours
    """

    if now is None:
        now = int(time.time())

    # Only trades that actually have a close time —
    # older data before this feature existed won't.
    dated_trades = [
        t for t in closed_trades
        if t.get("closed_timestamp") is not None
    ]

    sorted_trades = sorted(
        dated_trades, key=lambda t: t["closed_timestamp"]
    )

    # ------------------------------------------
    # Consecutive losses: walk backwards from the
    # most recent trade until a win breaks the streak
    # ------------------------------------------

    consecutive_losses = 0

    for trade in reversed(sorted_trades):
        if trade.get("result") == "STOP_LOSS":
            consecutive_losses += 1
        else:
            break

    # ------------------------------------------
    # Daily net P&L: everything closed in the
    # last 24 hours, wins and losses netted together
    # ------------------------------------------

    one_day_ago = now - (24 * 60 * 60)

    todays_trades = [
        t for t in sorted_trades
        if t["closed_timestamp"] >= one_day_ago
    ]

    # net_pnl_pct is the field paper_trade_utils.calculate_paper_pnl()
    # actually writes onto each closed trade. This previously read
    # "pnl_pct", a key that is never set, so daily_pnl_pct silently
    # evaluated to 0.0 on every call and the daily-loss pause could
    # never trigger. gross_pnl_pct is kept only as a last-resort
    # fallback for any legacy record that predates net_pnl_pct.
    daily_pnl_pct = sum(
        t.get("net_pnl_pct", t.get("gross_pnl_pct", 0.0)) or 0.0
        for t in todays_trades
    )

    # ------------------------------------------
    # Decide
    # ------------------------------------------

    if consecutive_losses >= max_consecutive_losses:
        return {
            "paused": True,
            "reason": (
                f"{consecutive_losses} consecutive stop-losses "
                f"(limit: {max_consecutive_losses})"
            ),
            "consecutive_losses": consecutive_losses,
            "daily_pnl_pct": daily_pnl_pct,
        }

    if daily_pnl_pct <= -abs(max_daily_loss_pct):
        return {
            "paused": True,
            "reason": (
                f"Daily loss of {daily_pnl_pct*100:.2f}% "
                f"exceeds the {max_daily_loss_pct*100:.1f}% limit"
            ),
            "consecutive_losses": consecutive_losses,
            "daily_pnl_pct": daily_pnl_pct,
        }

    return {
        "paused": False,
        "reason": None,
        "consecutive_losses": consecutive_losses,
        "daily_pnl_pct": daily_pnl_pct,
    }