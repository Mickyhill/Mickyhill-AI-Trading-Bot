# ==========================================
# ONE-TIME SCRIPT — run this once, then delete it
#
# Adds closed_timestamp to any already-CLOSED
# paper trade that's missing it (trades closed
# before circuit_breaker.py existed). Without
# this, the circuit breaker can't see those
# losses as part of a recent streak.
#
# We don't know the TRUE close time for these
# old trades, so we use right-now as a safe
# approximation — this errs toward the circuit
# breaker treating them as MORE recent (more
# cautious), never less.
# ==========================================

import json
import time

PAPER_FILE = "paper_trades.json"

with open(PAPER_FILE, "r", encoding="utf-8") as f:
    trades = json.load(f)

now = int(time.time())
fixed = 0

for trade in trades:
    if trade.get("status") == "CLOSED" and trade.get("closed_timestamp") is None:
        trade["closed_timestamp"] = now
        fixed += 1

with open(PAPER_FILE, "w", encoding="utf-8") as f:
    json.dump(trades, f, indent=2)

print(f"Backfilled closed_timestamp on {fixed} trade(s).")
print("You can delete this file now — it's a one-time fix, not needed again.") 