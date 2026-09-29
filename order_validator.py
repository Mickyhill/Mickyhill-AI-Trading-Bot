# ==========================================
# MickyHill AI Trading Bot
# order_validator.py
#
# Step 6C: validates a proposed order against
# Bybit's real rules for a symbol BEFORE any
# order is ever sent (Step 6D-F build the actual
# sending — this file only checks, never sends).
# ==========================================

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from bybit_api import get_symbol_info


# ==========================================
# ROUNDING HELPERS
#
# Using Decimal instead of plain float math —
# float step/tick rounding is a classic source
# of silent off-by-one-tick bugs.
# ==========================================

def round_down_to_step(value, step):
    """Rounds a quantity DOWN to the nearest valid step.
    Always rounds down for quantity — never round up,
    since that could risk more than intended."""

    if step is None or float(step) <= 0:
        return value

    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step))

    steps = (value_dec / step_dec).to_integral_value(rounding=ROUND_DOWN)

    return float(steps * step_dec)


def round_to_tick(value, tick_size):
    """Rounds a price to the nearest valid tick (normal
    rounding, not floor — prices aren't a safety concern
    the way quantity is)."""

    if tick_size is None or float(tick_size) <= 0:
        return value

    value_dec = Decimal(str(value))
    tick_dec = Decimal(str(tick_size))

    ticks = (value_dec / tick_dec).to_integral_value(rounding=ROUND_HALF_UP)

    return float(ticks * tick_dec)


# ==========================================
# MAIN VALIDATION FUNCTION
# ==========================================

def validate_order(
    symbol,
    direction,
    quantity,
    entry_price,
    stop_loss,
    take_profit,
    leverage,
):
    """
    Checks a proposed order against Bybit's real rules
    for this symbol. Does NOT send anything.

    Returns a dict:
      valid: True/False
      errors: list of strings — any reason(s) it's invalid
      adjusted: dict of quantity/entry/stop_loss/take_profit
                rounded to the symbol's real precision,
                for use ONCE an order is actually built (6D)
    """

    errors = []

    # ------------------------------------------
    # Symbol exists and is tradeable
    # ------------------------------------------

    info = get_symbol_info(symbol)

    if info is None:
        return {
            "valid": False,
            "errors": [f"Symbol {symbol} not found on Bybit"],
            "adjusted": None,
        }

    status = info.get("status")

    if status != "Trading":
        errors.append(
            f"Symbol {symbol} is not currently Trading (status: {status})"
        )

    # ------------------------------------------
    # Extract limits from Bybit's instrument info
    # ------------------------------------------

    lot_filter = info.get("lotSizeFilter", {})
    price_filter = info.get("priceFilter", {})
    leverage_filter = info.get("leverageFilter", {})

    min_qty = lot_filter.get("minOrderQty")
    max_qty = lot_filter.get("maxOrderQty")
    qty_step = lot_filter.get("qtyStep")
    min_notional = lot_filter.get("minNotionalValue")

    tick_size = price_filter.get("tickSize")

    max_leverage = leverage_filter.get("maxLeverage")
    min_leverage = leverage_filter.get("minLeverage")

    # ------------------------------------------
    # Directional sanity check
    # (catches a wrong sign before it becomes an order)
    # ------------------------------------------

    if direction == "BUY":
        if stop_loss >= entry_price:
            errors.append(
                f"BUY stop-loss ({stop_loss}) must be BELOW entry ({entry_price})"
            )
        if take_profit <= entry_price:
            errors.append(
                f"BUY take-profit ({take_profit}) must be ABOVE entry ({entry_price})"
            )

    elif direction == "SELL":
        if stop_loss <= entry_price:
            errors.append(
                f"SELL stop-loss ({stop_loss}) must be ABOVE entry ({entry_price})"
            )
        if take_profit >= entry_price:
            errors.append(
                f"SELL take-profit ({take_profit}) must be BELOW entry ({entry_price})"
            )
    else:
        errors.append(f"Unknown direction: {direction}")

    # ------------------------------------------
    # Round to valid precision
    # ------------------------------------------

    adjusted_qty = round_down_to_step(quantity, qty_step)
    adjusted_entry = round_to_tick(entry_price, tick_size)
    adjusted_stop = round_to_tick(stop_loss, tick_size)
    adjusted_target = round_to_tick(take_profit, tick_size)

    # ------------------------------------------
    # Quantity checks (AFTER rounding, since
    # rounding down can push a borderline qty
    # below the minimum)
    # ------------------------------------------

    if min_qty is not None and adjusted_qty < float(min_qty):
        errors.append(
            f"Quantity {adjusted_qty} is below minimum order quantity "
            f"{min_qty} for {symbol}"
        )

    if max_qty is not None and adjusted_qty > float(max_qty):
        errors.append(
            f"Quantity {adjusted_qty} exceeds maximum order quantity "
            f"{max_qty} for {symbol}"
        )

    if adjusted_qty <= 0:
        errors.append(
            "Quantity rounded down to zero — position is too small "
            "for this symbol's minimum step size"
        )

    # ------------------------------------------
    # Minimum notional value (order value in USDT)
    # ------------------------------------------

    if min_notional is not None:
        notional_value = adjusted_qty * adjusted_entry

        if notional_value < float(min_notional):
            errors.append(
                f"Order value ${notional_value:.2f} is below the minimum "
                f"order value of ${min_notional} for {symbol}"
            )

    # ------------------------------------------
    # Leverage checks
    # ------------------------------------------

    if max_leverage is not None and leverage > float(max_leverage):
        errors.append(
            f"Requested leverage {leverage}x exceeds this symbol's "
            f"maximum of {max_leverage}x"
        )

    if min_leverage is not None and leverage < float(min_leverage):
        errors.append(
            f"Requested leverage {leverage}x is below this symbol's "
            f"minimum of {min_leverage}x"
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "adjusted": {
            "quantity": adjusted_qty,
            "entry_price": adjusted_entry,
            "stop_loss": adjusted_stop,
            "take_profit": adjusted_target,
        },
    }