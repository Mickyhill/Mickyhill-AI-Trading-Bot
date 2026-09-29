# ==========================================
# Extension to backtester.py: detailed reporting
# (Average R, best/worst trade, breakdowns by
# symbol, direction, and confidence score)
# ==========================================


def compute_r_multiple(trade):
    """
    R-multiple = how many multiples of your initial risk you made or lost.
    +2.0 means you made 2x what you risked. -1.0 means you lost
    exactly what you risked (a clean stop-out).
    """
    entry = trade["entry"]
    stop = trade["stop_loss"]

    risk_pct = abs(entry - stop) / entry

    if risk_pct == 0:
        return 0.0

    return trade["pnl_pct"] / risk_pct


def score_bucket(score):
    """Groups scores into bands of 10: 70-79, 80-89, etc."""
    low = (score // 10) * 10
    return f"{low}-{low + 9}"


def breakdown_by(trades, key_func):
    """
    Generic grouping helper. Returns a dict like:
    { "SOLUSDT": {"trades": 5, "wins": 3, "win_rate_pct": 60.0, "total_return_pct": 4.2}, ... }
    Only considers WIN/LOSS trades (not TIMEOUT).
    """
    closed = [t for t in trades if t["result"] in ("WIN", "LOSS")]

    groups = {}

    for t in closed:
        key = key_func(t)
        groups.setdefault(key, []).append(t)

    result = {}

    for key, group_trades in groups.items():
        wins = [t for t in group_trades if t["result"] == "WIN"]
        n = len(group_trades)

        result[key] = {
            "trades": n,
            "wins": len(wins),
            "win_rate_pct": round((len(wins) / n) * 100, 1) if n else 0.0,
            "total_return_pct": round(
                sum(t["pnl_pct"] for t in group_trades) * 100, 2
            ),
        }

    return result


def generate_full_report(trades):
    """
    Builds the complete report matching every metric requested:
    totals, win rate, return, profit factor, drawdown, average R,
    best/worst trade, and breakdowns by symbol / direction / score.
    """

    from backtester import compute_stats

    overall = compute_stats(trades)

    closed = [t for t in trades if t["result"] in ("WIN", "LOSS")]

    if not closed:
        overall["average_r"] = None
        overall["best_trade"] = None
        overall["worst_trade"] = None
        overall["by_symbol"] = {}
        overall["by_direction"] = {}
        overall["by_score_bucket"] = {}
        return overall

    r_multiples = [compute_r_multiple(t) for t in closed]
    overall["average_r"] = round(sum(r_multiples) / len(r_multiples), 2)

    best = max(closed, key=lambda t: t["pnl_pct"])
    worst = min(closed, key=lambda t: t["pnl_pct"])

    overall["best_trade"] = {
        "symbol": best["symbol"],
        "direction": best["direction"],
        "score": best["score"],
        "pnl_pct": round(best["pnl_pct"] * 100, 2),
    }
    overall["worst_trade"] = {
        "symbol": worst["symbol"],
        "direction": worst["direction"],
        "score": worst["score"],
        "pnl_pct": round(worst["pnl_pct"] * 100, 2),
    }

    overall["by_symbol"] = breakdown_by(trades, lambda t: t["symbol"])
    overall["by_direction"] = breakdown_by(trades, lambda t: t["direction"])
    overall["by_score_bucket"] = breakdown_by(
        trades, lambda t: score_bucket(t["score"])
    )

    return overall


def print_full_report(trades):

    report = generate_full_report(trades)

    print("\n" + "=" * 70)
    print("FULL BACKTEST REPORT")
    print("=" * 70)

    print(f"\nTotal trades (closed):  {report.get('num_trades')}")
    print(f"Timeouts (excluded):    {report.get('num_timeouts')}")
    print(f"Win rate:               {report.get('win_rate_pct')}%")
    print(f"Loss rate:              {report.get('loss_rate_pct')}%")
    print(f"Profit factor:          {report.get('profit_factor')}")
    print(f"Average win:            {report.get('avg_win_pct')}%")
    print(f"Average loss:           {report.get('avg_loss_pct')}%")
    print(f"Average R:              {report.get('average_r')}")
    print(f"Expectancy per trade:   {report.get('expectancy_pct_per_trade')}%")
    print(f"Max drawdown:           {report.get('max_drawdown_pct')}%")
    print(f"Max consecutive losses: {report.get('max_consecutive_losses')}")
    print(f"Total return:           {report.get('total_return_pct')}%")

    if report.get("best_trade"):
        b = report["best_trade"]
        print(
            f"\nBest trade:  {b['symbol']} {b['direction']} "
            f"score={b['score']} pnl={b['pnl_pct']}%"
        )

    if report.get("worst_trade"):
        w = report["worst_trade"]
        print(
            f"Worst trade: {w['symbol']} {w['direction']} "
            f"score={w['score']} pnl={w['pnl_pct']}%"
        )

    print("\n--- Results by symbol ---")
    for symbol, stats in report.get("by_symbol", {}).items():
        print(
            f"  {symbol}: {stats['trades']} trades, "
            f"{stats['win_rate_pct']}% win rate, "
            f"{stats['total_return_pct']}% return"
        )

    print("\n--- Results by direction ---")
    for direction, stats in report.get("by_direction", {}).items():
        print(
            f"  {direction}: {stats['trades']} trades, "
            f"{stats['win_rate_pct']}% win rate, "
            f"{stats['total_return_pct']}% return"
        )

    print("\n--- Results by confidence score ---")
    for bucket, stats in sorted(report.get("by_score_bucket", {}).items()):
        print(
            f"  {bucket}: {stats['trades']} trades, "
            f"{stats['win_rate_pct']}% win rate, "
            f"{stats['total_return_pct']}% return"
        )