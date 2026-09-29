# ==========================================
# MickyHill AI Trading Bot
# order_builder.py
#
# Step 6D: constructs the exact parameters a real
# Bybit order would need.
#
# THIS FILE NEVER SENDS AN ORDER. There is no
# session.place_order() call anywhere in it, and
# there must not be one added here — that is
# Step 6F's job, behind the hard execution gate
# in main.py (Step 6E). This file only builds and
# previews what an order WOULD look like.
#
# OPEN DESIGN QUESTION (not silently resolved):
# The strategy produces THREE take-profit levels
# (TP1/TP2/TP3), but Bybit's native order only
# supports ONE stop-loss and ONE take-profit.
# This builder uses TP2 as the native target,
# since that's the level the backtester actually
# simulated against. TP1/TP3 are not yet handled
# by anything — hitting them would require either
# partial-close orders or manual position
# management, neither of which exists yet.
# ==========================================

from order_validator import validate_order


# ==========================================
# ASSUMPTIONS — worth checking before Step 6F
# ==========================================

# One-way position mode (not hedge mode).
# If your Bybit account uses hedge mode, positionIdx
# below needs to be 1 (long) / 2 (short) instead of 0.
POSITION_IDX = 0

# Limit order at the computed entry price, not a
# market order — this avoids slippage but means the
# order might not fill if price moves away first.
ORDER_TYPE = "Limit"
TIME_IN_FORCE = "GTC"


# ==========================================
# BUILD ORDER PARAMETERS
# ==========================================

def build_order_preview(
    symbol,
    direction,
    quantity,
    entry_price,
    stop_loss,
    take_profit_2,
    leverage,
):
    """
    Validates the setup, then constructs the exact
    dict of parameters a Bybit order would use.

    Returns:
      built: True/False
      errors: list of strings (why it wasn't built, if not)
      order_params: the dict ready for a future
                     session.place_order(**order_params)
                     call — NOT called here
      preview_text: human-readable summary
    """

    validation = validate_order(
        symbol=symbol,
        direction=direction,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit_2,
        leverage=leverage,
    )

    if not validation["valid"]:
        return {
            "built": False,
            "errors": validation["errors"],
            "order_params": None,
            "preview_text": None,
        }

    adjusted = validation["adjusted"]

    side = "Buy" if direction == "BUY" else "Sell"

    order_params = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": ORDER_TYPE,
        "qty": str(adjusted["quantity"]),
        "price": str(adjusted["entry_price"]),
        "timeInForce": TIME_IN_FORCE,
        "stopLoss": str(adjusted["stop_loss"]),
        "takeProfit": str(adjusted["take_profit"]),
        "positionIdx": POSITION_IDX,
        "reduceOnly": False,
    }

    preview_text = (
        f"[PREVIEW ONLY — NOT SENT]\n"
        f"{side} {order_params['qty']} {symbol} @ {order_params['price']} "
        f"({ORDER_TYPE}, leverage {leverage}x)\n"
        f"  Stop-loss:   {order_params['stopLoss']}\n"
        f"  Take-profit: {order_params['takeProfit']} (TP2 — TP1/TP3 not handled yet)"
    )

    return {
        "built": True,
        "errors": [],
        "order_params": order_params,
        "preview_text": preview_text,
    }