# ==========================================
# MickyHill AI Trading Bot
# risk_manager.py
#
# Turns a trade setup (entry, stop-loss) into an
# actual position size, based on your real account
# balance and a fixed risk percentage per trade.
#
# This REPLACES trend-based leverage suggestions.
# Leverage here is a CONSEQUENCE of position sizing,
# never a way to increase how much you're risking.
# ==========================================

from bybit_api import get_wallet_balance
from config import RISK_PER_TRADE, DEFAULT_LEVERAGE


# ==========================================
# SETTINGS
#
# Pulled from config.py — single source of
# truth, not duplicated here.
# ==========================================

RISK_PER_TRADE_PCT = RISK_PER_TRADE
MAX_LEVERAGE = DEFAULT_LEVERAGE


# ==========================================
# GET AVAILABLE ACCOUNT BALANCE
# ==========================================

def get_account_balance_usdt():
    """
    Pulls your actual USDT balance from Bybit.
    Returns None if it can't be read (caller must
    handle this — never guess a balance).
    """

    try:
        response = get_wallet_balance()

        accounts = (
            response
            .get("result", {})
            .get("list", [])
        )

        if not accounts:
            return None

        coins = accounts[0].get("coin", [])

        for coin in coins:
            if coin.get("coin") == "USDT":
                balance = coin.get("walletBalance") or coin.get("availableToWithdraw")
                if balance is None:
                    return None
                return float(balance)

        return None

    except Exception:
        return None


# ==========================================
# CALCULATE POSITION SIZE
# ==========================================

def calculate_position_size(
    account_balance_usdt,
    entry_price,
    stop_loss_price,
    risk_pct=RISK_PER_TRADE_PCT,
    max_leverage=MAX_LEVERAGE,
):
    """
    Given your account balance and a trade's entry/stop,
    works out exactly how big the position should be so
    that a stop-out costs exactly risk_pct of your account
    — never more, regardless of how far away the stop is.

    Returns a dict with everything needed to actually place
    the trade, or a dict with "error" set if the setup can't
    be sized safely.
    """

    if account_balance_usdt is None or account_balance_usdt <= 0:
        return {"error": "No valid account balance available"}

    stop_distance = abs(entry_price - stop_loss_price)

    if stop_distance <= 0:
        return {"error": "Stop-loss distance is zero — cannot size position"}

    # How much money (in USDT) you're willing to lose on this trade
    risk_amount_usdt = account_balance_usdt * risk_pct

    # How many coins/contracts that risk amount buys you,
    # given how far away the stop is
    position_size_units = risk_amount_usdt / stop_distance

    # Total notional value of that position
    position_value_usdt = position_size_units * entry_price

    # Leverage needed to open a position this size —
    # this is a RESULT of the sizing, not a choice made
    # independently of risk
    required_leverage = position_value_usdt / account_balance_usdt

    warning = None

    if required_leverage > max_leverage:
        # The math wants more leverage than our safety ceiling
        # allows. Rather than exceed the cap, shrink the
        # position — this means the ACTUAL risk taken will be
        # less than risk_pct, which is the safe direction to
        # be wrong in.
        capped_leverage = max_leverage
        position_value_usdt = account_balance_usdt * capped_leverage
        position_size_units = position_value_usdt / entry_price
        actual_risk_usdt = position_size_units * stop_distance
        actual_risk_pct = actual_risk_usdt / account_balance_usdt

        warning = (
            f"Stop is tight relative to account size — required leverage "
            f"({required_leverage:.1f}x) exceeded the {max_leverage}x safety cap. "
            f"Position size was reduced. Actual risk on this trade is "
            f"{actual_risk_pct*100:.2f}% instead of the target {risk_pct*100:.1f}%."
        )

        required_leverage = capped_leverage
        risk_amount_usdt = actual_risk_usdt

    return {
        "account_balance_usdt": round(account_balance_usdt, 2),
        "risk_amount_usdt": round(risk_amount_usdt, 2),
        "risk_pct_used": round((risk_amount_usdt / account_balance_usdt) * 100, 3),
        "position_size_units": position_size_units,
        "position_value_usdt": round(position_value_usdt, 2),
        "required_leverage": round(required_leverage, 2),
        "warning": warning,
    }