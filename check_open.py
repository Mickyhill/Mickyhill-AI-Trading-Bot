import sqlite3

db = sqlite3.connect("paper_trades.db")

rows = db.execute(
    "SELECT symbol, direction, COUNT(*) "
    "FROM paper_trades "
    "WHERE status = ? "
    "GROUP BY symbol, direction",
    ("OPEN",)
).fetchall()

print("OPEN TRADES:")
for row in rows:
    print(row)

db.close()