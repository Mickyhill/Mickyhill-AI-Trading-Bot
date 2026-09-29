from paper_trade_utils import calculate_paper_pnl


def approx(a, b, tol=1e-9):
    assert abs(a - b) < tol, (a, b)


def test_buy_net_pnl_and_fees():
    trade = {
        "direction": "BUY",
        "entry": 100.0,
        "sizing": {
            "position_size_units": 1.0,
            "risk_amount_usdt": 1.0,
        },
    }
    result = calculate_paper_pnl(trade, 102.0, 0.0012)
    approx(result["gross_pnl_usdt"], 2.0)
    approx(result["fees_usdt"], (100.0 + 102.0) * 0.0006)
    approx(result["net_pnl_usdt"], 2.0 - (202.0 * 0.0006))
    approx(result["r_multiple"], result["net_pnl_usdt"] / 1.0)


def test_sell_net_pnl_and_fees():
    trade = {
        "direction": "SELL",
        "entry": 100.0,
        "sizing": {
            "position_size_units": 2.0,
            "risk_amount_usdt": 2.0,
        },
    }
    result = calculate_paper_pnl(trade, 98.0, 0.0012)
    approx(result["gross_pnl_usdt"], 4.0)
    approx(result["fees_usdt"], (200.0 + 196.0) * 0.0006)
    approx(result["net_pnl_usdt"], 4.0 - (396.0 * 0.0006))


def test_old_trade_without_sizing_still_gets_percentage_accounting():
    trade = {
        "direction": "BUY",
        "entry": 100.0,
    }
    result = calculate_paper_pnl(trade, 99.0, 0.0012)
    assert result["gross_pnl_usdt"] is None
    assert result["net_pnl_usdt"] is None
    assert result["net_pnl_pct"] < result["gross_pnl_pct"]


if __name__ == "__main__":
    test_buy_net_pnl_and_fees()
    test_sell_net_pnl_and_fees()
    test_old_trade_without_sizing_still_gets_percentage_accounting()
    print("PASS: paper-trade accounting tests")
