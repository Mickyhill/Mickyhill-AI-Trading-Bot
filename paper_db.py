# ==========================================
# MickyHill AI Trading Bot
# paper_db.py
# Persistent SQLite storage for paper trades/events.
# ==========================================

import csv
import json
import os
import sqlite3
import time
import uuid


DB_FILE = "paper_trades.db"
LEGACY_JSON = "paper_trades.json"
EXPORT_FILE = "paper_trades_export.csv"


# ==========================================
# DATABASE CONNECTION
# ==========================================

def _connect():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn


# ==========================================
# CLEAN UP PRE-EXISTING DUPLICATE OPEN TRADES
#
# Only relevant once, for databases that predate the
# unique-open-trade rule below. Keeps the OLDEST open
# trade for each (symbol, direction) pair and marks any
# others CLOSED with final_result='DUPLICATE_CLEANUP' —
# the same status already used for this exact situation
# in this database. Safe to call every startup: once
# cleaned, there is nothing left to find.
# ==========================================

def _cleanup_duplicate_open_trades(conn):

    rows = conn.execute(
        """
        SELECT trade_id, symbol, direction, opened_timestamp
        FROM paper_trades
        WHERE status = 'OPEN'
        ORDER BY symbol, direction, opened_timestamp ASC
        """
    ).fetchall()

    seen = set()
    cleaned = 0

    for row in rows:
        key = (row["symbol"], row["direction"])

        if key in seen:
            conn.execute(
                """
                UPDATE paper_trades
                SET status = 'CLOSED',
                    final_result = 'DUPLICATE_CLEANUP'
                WHERE trade_id = ?
                """,
                (row["trade_id"],),
            )
            cleaned += 1
        else:
            seen.add(key)

    if cleaned:
        print(
            f"🧹 Cleaned up {cleaned} pre-existing duplicate OPEN "
            f"trade(s) before enforcing the uniqueness rule."
        )


# ==========================================
# INITIALIZE DATABASE
# ==========================================

def init_db():
    with _connect() as conn:

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            signal_time INTEGER,
            opened_timestamp INTEGER NOT NULL,

            entry REAL NOT NULL,
            stop_loss REAL NOT NULL,

            take_profit_1 REAL NOT NULL,
            take_profit_2 REAL NOT NULL,
            take_profit_3 REAL NOT NULL,

            confidence REAL,

            status TEXT NOT NULL,

            tp1_hit INTEGER NOT NULL DEFAULT 0,
            tp2_hit INTEGER NOT NULL DEFAULT 0,
            tp3_hit INTEGER NOT NULL DEFAULT 0,
            sl_hit INTEGER NOT NULL DEFAULT 0,

            targets_hit TEXT NOT NULL DEFAULT '[]',

            exit_time INTEGER,
            exit_price REAL,
            final_result TEXT,

            current_price REAL,

            last_event_time INTEGER,
            last_event_price REAL,
            last_event TEXT,

            sizing_json TEXT,
            extra_json TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,

            trade_id TEXT NOT NULL,
            event_type TEXT NOT NULL,

            event_time INTEGER NOT NULL,
            event_price REAL NOT NULL,

            UNIQUE(trade_id, event_type),

            FOREIGN KEY(trade_id)
                REFERENCES paper_trades(trade_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_paper_trades_status
            ON paper_trades(status);

        CREATE INDEX IF NOT EXISTS idx_trade_events_trade
            ON trade_events(trade_id);

        CREATE TABLE IF NOT EXISTS bot_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # ------------------------------------------
        # Clean up any pre-existing duplicate OPEN
        # trades BEFORE enforcing uniqueness, or the
        # index creation below would fail outright
        # against data that already breaks the rule.
        # Safe to run every startup — once cleaned,
        # there's nothing left to find.
        # ------------------------------------------

        _cleanup_duplicate_open_trades(conn)

        # ------------------------------------------
        # Makes duplicate open trades IMPOSSIBLE, not
        # just checked-for. Before this, insert_trade()
        # checked has_open_trade() and then inserted as
        # two separate steps — nothing stopped two
        # different running processes from both passing
        # that check at nearly the same instant and both
        # inserting. A partial unique index means SQLite
        # itself refuses the second insert, no matter how
        # many processes are running or how they're timed.
        # ------------------------------------------

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_open_trade
            ON paper_trades(symbol, direction)
            WHERE status = 'OPEN'
        """)

    migrate_legacy_json()


# ==========================================
# MIGRATE OLD JSON DATA
# ==========================================

def migrate_legacy_json():

    # This import is meant to run exactly once. Because legacy JSON trades
    # have no stable trade_id, re-running this on every bot startup would
    # generate a brand-new random UUID per trade each time and silently
    # duplicate the whole legacy backlog (INSERT OR IGNORE can't catch a
    # different UUID on every run). Renaming the source file after a
    # successful import makes this function idempotent across restarts.
    if not os.path.exists(LEGACY_JSON):
        return

    try:
        with open(
            LEGACY_JSON,
            "r",
            encoding="utf-8"
        ) as f:
            trades = json.load(f)

    except Exception:
        return

    if not isinstance(trades, list):
        return

    with _connect() as conn:

        for trade in trades:

            trade_id = (
                trade.get("trade_id")
                or str(uuid.uuid4())
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO paper_trades (
                    trade_id,
                    symbol,
                    direction,
                    signal_time,
                    opened_timestamp,

                    entry,
                    stop_loss,
                    take_profit_1,
                    take_profit_2,
                    take_profit_3,

                    confidence,
                    status,

                    tp1_hit,
                    tp2_hit,
                    tp3_hit,
                    sl_hit,

                    targets_hit,

                    exit_time,
                    exit_price,
                    final_result,

                    current_price,

                    last_event_time,
                    last_event_price,
                    last_event,

                    sizing_json,
                    extra_json
                )

                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?,
                    ?, ?, ?,
                    ?,
                    ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    trade_id,

                    trade.get("symbol"),
                    trade.get("direction"),

                    trade.get(
                        "signal_time",
                        trade.get("timestamp")
                    ),

                    trade.get(
                        "opened_timestamp",
                        trade.get(
                            "timestamp",
                            int(time.time())
                        )
                    ),

                    float(
                        trade.get("entry", 0)
                    ),

                    float(
                        trade.get("stop_loss", 0)
                    ),

                    float(
                        trade.get(
                            "take_profit_1",
                            0
                        )
                    ),

                    float(
                        trade.get(
                            "take_profit_2",
                            0
                        )
                    ),

                    float(
                        trade.get(
                            "take_profit_3",
                            0
                        )
                    ),

                    trade.get(
                        "confidence",
                        trade.get("score")
                    ),

                    trade.get(
                        "status",
                        "OPEN"
                    ),

                    int(
                        "TP1"
                        in trade.get(
                            "targets_hit",
                            []
                        )
                    ),

                    int(
                        "TP2"
                        in trade.get(
                            "targets_hit",
                            []
                        )
                    ),

                    int(
                        "TP3"
                        in trade.get(
                            "targets_hit",
                            []
                        )
                    ),

                    int(
                        trade.get("result")
                        == "STOP_LOSS"
                    ),

                    json.dumps(
                        trade.get(
                            "targets_hit",
                            []
                        )
                    ),

                    trade.get(
                        "closed_timestamp"
                    ),

                    trade.get(
                        "exit_price"
                    ),

                    trade.get(
                        "result"
                    ),

                    trade.get(
                        "current_price"
                    ),

                    None,
                    None,

                    trade.get(
                        "last_target"
                    ),

                    json.dumps(
                        trade.get(
                            "sizing",
                            {}
                        )
                    ),

                    json.dumps(trade)
                )
            )

            # ----------------------------------
            # Restore target events
            # ----------------------------------

            for target in trade.get(
                "targets_hit",
                []
            ):

                event_time = (
                    trade.get("closed_timestamp")
                    or trade.get("timestamp")
                    or int(time.time())
                )

                event_price = (
                    trade.get("exit_price")
                    or trade.get("entry")
                )

                conn.execute(
                    """
                    INSERT OR IGNORE INTO trade_events
                    (
                        trade_id,
                        event_type,
                        event_time,
                        event_price
                    )

                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        trade_id,
                        target,
                        event_time,
                        float(event_price)
                    )
                )

            # ----------------------------------
            # Restore SL event
            # ----------------------------------

            if trade.get("result") == "STOP_LOSS":

                conn.execute(
                    """
                    INSERT OR IGNORE INTO trade_events
                    (
                        trade_id,
                        event_type,
                        event_time,
                        event_price
                    )

                    VALUES (?, 'SL', ?, ?)
                    """,
                    (
                        trade_id,

                        trade.get(
                            "closed_timestamp",
                            int(time.time())
                        ),

                        float(
                            trade.get(
                                "exit_price",
                                trade.get(
                                    "entry",
                                    0
                                )
                            )
                        )
                    )
                )

    # Import complete. Rename the source file so this function becomes a
    # no-op on every future call (bot restart, re-import, etc). Nothing
    # reads paper_trades.json after this point, so the data is safe.
    try:
        os.replace(LEGACY_JSON, LEGACY_JSON + ".migrated")
    except OSError as exc:
        print(f"⚠️ Could not rename {LEGACY_JSON} after migration: {exc}")


# ==========================================
# INSERT PAPER TRADE
# ==========================================

def insert_trade(trade):

    trade = dict(trade)

    symbol = trade.get("symbol")
    direction = trade.get("direction")

    if symbol and direction and has_open_trade(symbol, direction):
        print(
            f"⏭️ Duplicate paper trade blocked: "
            f"{symbol} {direction}"
        )
        return None

    trade_id = (
        trade.get("trade_id")
        or str(uuid.uuid4())
    )

    trade["trade_id"] = trade_id

    now = int(time.time())

    trade.setdefault(
        "signal_time",
        trade.get("timestamp", now)
    )

    trade.setdefault(
        "opened_timestamp",
        now
    )

    trade.setdefault(
        "status",
        "OPEN"
    )

    trade.setdefault(
        "targets_hit",
        []
    )

    with _connect() as conn:

        try:
            conn.execute(
                """
                INSERT INTO paper_trades (

                    trade_id,
                    symbol,
                    direction,
                    signal_time,
                    opened_timestamp,

                    entry,
                    stop_loss,

                    take_profit_1,
                    take_profit_2,
                    take_profit_3,

                    confidence,
                    status,

                    targets_hit,

                    sizing_json,
                    extra_json
                )

                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?
                )
                """,
                (
                    trade_id,

                    trade["symbol"],
                    trade["direction"],

                    trade["signal_time"],
                    trade["opened_timestamp"],

                    float(
                        trade["entry"]
                    ),

                    float(
                        trade["stop_loss"]
                    ),

                    float(
                        trade["take_profit_1"]
                    ),

                    float(
                        trade["take_profit_2"]
                    ),

                    float(
                        trade["take_profit_3"]
                    ),

                    trade.get("score"),

                    trade["status"],

                    json.dumps(
                        trade["targets_hit"]
                    ),

                    json.dumps(
                        trade.get(
                            "sizing",
                            {}
                        )
                    ),

                    json.dumps(trade)
                )
            )

        except sqlite3.IntegrityError:
            # The has_open_trade() check above is a fast pre-check, but
            # the UNIQUE INDEX on (symbol, direction) WHERE status='OPEN'
            # is the real, race-proof guard — this catches the case where
            # another process inserted the same open trade in the tiny
            # gap between our check and our insert.
            print(
                f"⏭️ Duplicate paper trade blocked at the database level: "
                f"{trade['symbol']} {trade['direction']}"
            )
            return None

    print(
        f"📝 PAPER TRADE RECORDED: {trade_id}"
    )

    return trade_id


# ==========================================
# CONVERT DATABASE ROW TO TRADE DICT
# ==========================================

def _row_to_trade(row):

    if row is None:
        return None

    trade = dict(row)

    # --------------------------------------
    # Targets
    # --------------------------------------

    try:
        trade["targets_hit"] = json.loads(
            trade.pop("targets_hit")
            or "[]"
        )
    except Exception:
        trade["targets_hit"] = []

    # --------------------------------------
    # Position sizing
    # --------------------------------------

    try:
        trade["sizing"] = json.loads(
            trade.pop("sizing_json")
            or "{}"
        )
    except Exception:
        trade["sizing"] = {}

    # --------------------------------------
    # Extra trade information
    # --------------------------------------

    try:
        extra = json.loads(
            trade.pop("extra_json")
            or "{}"
        )
    except Exception:
        extra = {}

    for key, value in extra.items():
        trade.setdefault(
            key,
            value
        )

    trade["trade_id"] = row["trade_id"]

    return trade


# ==========================================
# GET OPEN TRADES
# ==========================================

def get_open_trades():

    with _connect() as conn:

        rows = conn.execute(
            """
            SELECT *
            FROM paper_trades

            WHERE status = 'OPEN'

            ORDER BY opened_timestamp ASC
            """
        ).fetchall()

    return [
        _row_to_trade(row)
        for row in rows
    ]


# ==========================================
# GET ALL TRADES
# ==========================================

def get_all_trades(limit=None):

    sql = """
        SELECT *
        FROM paper_trades
        ORDER BY opened_timestamp DESC
    """

    params = ()

    if limit:

        sql += " LIMIT ?"

        params = (
            int(limit),
        )

    with _connect() as conn:

        rows = conn.execute(
            sql,
            params
        ).fetchall()

    return [
        _row_to_trade(row)
        for row in rows
    ]


# ==========================================
# CHECK IF SYMBOL ALREADY HAS OPEN TRADE
# ==========================================

def has_open_trade(
    symbol,
    direction
):

    with _connect() as conn:

        row = conn.execute(
            """
            SELECT trade_id
            FROM paper_trades

            WHERE symbol = ?
              AND direction = ?
              AND status = 'OPEN'

            LIMIT 1
            """,
            (
                symbol,
                direction
            )
        ).fetchone()

    return row is not None


# ==========================================
# UPDATE CURRENT PRICE
# ==========================================

def update_current_price(
    trade_id,
    price
):

    with _connect() as conn:

        conn.execute(
            """
            UPDATE paper_trades

            SET current_price = ?

            WHERE trade_id = ?
            """,
            (
                float(price),
                trade_id
            )
        )


# ==========================================
# UPDATE STOP LOSS
# (used to move the stop to breakeven once a
# trade proves itself by hitting TP1)
# ==========================================

def update_stop_loss(trade_id, new_stop_loss):
    """
    Updates stop_loss for an OPEN trade only. Returns True if a row
    was actually updated, False if the trade was not found or was
    already closed (e.g. it hit TP3/SL in the same instant this was
    attempted — the OPEN guard prevents rewriting a closed trade's
    stop after the fact).
    """

    with _connect() as conn:

        cursor = conn.execute(
            """
            UPDATE paper_trades

            SET stop_loss = ?

            WHERE trade_id = ?
              AND status = 'OPEN'
            """,
            (
                float(new_stop_loss),
                trade_id,
            )
        )

        return cursor.rowcount > 0


# ==========================================
# BOT STATE (small persisted key/value store)
# Used for things like the manual circuit-breaker
# reset marker — not trade data.
# ==========================================

def set_state(key, value):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def get_state(key, default=None):
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM bot_state WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else default


# ==========================================
# RECORD EVENT ONCE
# ==========================================

def record_event_once(
    trade_id,
    event_type,
    event_time,
    event_price
):

    with _connect() as conn:

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO trade_events
            (
                trade_id,
                event_type,
                event_time,
                event_price
            )

            VALUES (?, ?, ?, ?)
            """,
            (
                trade_id,
                event_type,
                int(event_time),
                float(event_price)
            )
        )

        return cur.rowcount == 1


# ==========================================
# MARK TARGET AS HIT
# ==========================================

def mark_target_hit(
    trade_id,
    target,
    event_time,
    event_price
):

    # --------------------------------------
    # Prevent duplicate Telegram events
    # --------------------------------------

    if not record_event_once(
        trade_id,
        target,
        event_time,
        event_price
    ):
        return False

    column = {
        "TP1": "tp1_hit",
        "TP2": "tp2_hit",
        "TP3": "tp3_hit"
    }[target]

    with _connect() as conn:

        row = conn.execute(
            """
            SELECT targets_hit
            FROM paper_trades

            WHERE trade_id = ?
            """,
            (trade_id,)
        ).fetchone()

        if row:

            try:
                targets = json.loads(
                    row[0] or "[]"
                )
            except Exception:
                targets = []

        else:
            targets = []

        if target not in targets:
            targets.append(target)

        conn.execute(
            f"""
            UPDATE paper_trades

            SET
                {column} = 1,
                targets_hit = ?,
                last_event_time = ?,
                last_event_price = ?,
                last_event = ?

            WHERE trade_id = ?
              AND status = 'OPEN'
            """,
            (
                json.dumps(targets),
                int(event_time),
                float(event_price),
                target,
                trade_id
            )
        )

    return True


# ==========================================
# CLOSE TRADE
# ==========================================

def close_trade(
    trade_id,
    result,
    event_time,
    exit_price,
    accounting
):

    event_type = (
        "SL"
        if result == "STOP_LOSS"
        else "TP3"
    )

    with _connect() as conn:

        # ----------------------------------
        # Make sure trade is still OPEN
        # ----------------------------------

        row = conn.execute(
            """
            SELECT status
            FROM paper_trades

            WHERE trade_id = ?
            """,
            (trade_id,)
        ).fetchone()

        if (
            not row
            or row["status"] != "OPEN"
        ):
            return False

        # ----------------------------------
        # Record terminal event once
        # ----------------------------------

        conn.execute(
            """
            INSERT OR IGNORE INTO trade_events
            (
                trade_id,
                event_type,
                event_time,
                event_price
            )

            VALUES (?, ?, ?, ?)
            """,
            (
                trade_id,
                event_type,
                int(event_time),
                float(exit_price)
            )
        )

        # ----------------------------------
        # Prepare accounting data
        # ----------------------------------

        extra = conn.execute(
            """
            SELECT extra_json
            FROM paper_trades

            WHERE trade_id = ?
            """,
            (trade_id,)
        ).fetchone()

        try:
            extra_data = json.loads(
                extra[0] or "{}"
            )
        except Exception:
            extra_data = {}

        if accounting:
            extra_data.update(
                accounting
            )

        extra_data["result"] = result

        extra_data[
            "closed_timestamp"
        ] = int(event_time)

        # ----------------------------------
        # Close trade
        # ----------------------------------

        conn.execute(
            """
            UPDATE paper_trades

            SET
                status = ?,
                final_result = ?,
                exit_time = ?,
                exit_price = ?,

                last_event_time = ?,
                last_event_price = ?,
                last_event = ?,

                extra_json = ?

            WHERE trade_id = ?
            """,
            (
                "CLOSED",

                result,

                int(event_time),

                float(exit_price),

                int(event_time),

                float(exit_price),

                event_type,

                json.dumps(
                    extra_data
                ),

                trade_id
            )
        )

    return True


# ==========================================
# EXPORT TRADES TO CSV
# ==========================================

def export_csv(
    path=EXPORT_FILE
):

    trades = get_all_trades()

    if not trades:
        return path

    keys = [
        "trade_id",
        "symbol",
        "direction",

        "signal_time",
        "opened_timestamp",

        "entry",
        "stop_loss",

        "take_profit_1",
        "take_profit_2",
        "take_profit_3",

        "confidence",
        "status",

        "targets_hit",

        "exit_time",
        "exit_price",
        "final_result",

        "gross_pnl_pct",
        "net_pnl_pct",

        "gross_pnl_usdt",
        "fees_usdt",
        "net_pnl_usdt",

        "r_multiple"
    ]

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=keys,
            extrasaction="ignore"
        )

        writer.writeheader()

        for trade in trades:
            writer.writerow(trade)

    return path