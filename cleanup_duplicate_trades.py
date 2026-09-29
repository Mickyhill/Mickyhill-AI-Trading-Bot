# ==========================================
# MickyHill AI Trading Bot
# cleanup_duplicate_trades.py
#
# ONE-TIME cleanup for OPEN trades duplicated by the
# migrate_legacy_json() restart bug (fixed in paper_db.py).
#
# For each (symbol, direction) group of OPEN trades, this keeps
# only the EARLIEST row (by opened_timestamp) and closes the rest
# with final_result = "DUPLICATE_CLEANUP" so they no longer count
# as open positions and remain visible in Trade History for audit.
#
# Nothing is deleted. Run it once, from the project folder:
#     python cleanup_duplicate_trades.py
# Add --dry-run first if you want to see what it would do before
# it touches anything.
# ==========================================

import argparse
import sqlite3
import time

DB_FILE = "paper_trades.db"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would change without writing anything.")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row

    groups = conn.execute(
        """
        SELECT symbol, direction, COUNT(*) AS c
        FROM paper_trades
        WHERE status = 'OPEN'
        GROUP BY symbol, direction
        HAVING c > 1
        """
    ).fetchall()

    if not groups:
        print("No duplicate OPEN trades found. Nothing to do.")
        return

    total_closed = 0
    now = int(time.time())

    for g in groups:
        rows = conn.execute(
            """
            SELECT trade_id, opened_timestamp
            FROM paper_trades
            WHERE symbol = ? AND direction = ? AND status = 'OPEN'
            ORDER BY opened_timestamp ASC, trade_id ASC
            """,
            (g["symbol"], g["direction"]),
        ).fetchall()

        keep = rows[0]
        drop = rows[1:]

        print(
            f"{g['symbol']} {g['direction']}: keeping {keep['trade_id']} "
            f"(opened {keep['opened_timestamp']}), closing {len(drop)} duplicate(s)"
        )

        for row in drop:
            if args.dry_run:
                print(f"    [dry-run] would close {row['trade_id']}")
                continue
            conn.execute(
                """
                UPDATE paper_trades
                SET status = 'CLOSED',
                    final_result = 'DUPLICATE_CLEANUP',
                    exit_time = ?
                WHERE trade_id = ?
                """,
                (now, row["trade_id"]),
            )
            total_closed += 1

    if args.dry_run:
        print("\nDry run complete. No changes were made.")
    else:
        conn.commit()
        print(f"\nDone. Closed {total_closed} duplicate row(s). "
              f"Restart the bot and check 'Active Trades' to confirm counts look right.")

    conn.close()


if __name__ == "__main__":
    main()