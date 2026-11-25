"""Legacy SQLite format, retained only for offline migration fixtures. Not in worker image."""
import sqlite3
import time
from pathlib import Path

class UsageLedger:
    """Atomic, global, lifetime reservations; failures retain their full reservation.

    Requires one durable volume shared by all workers. Multi-host deployments must
    use a transactional central ledger before enabling inference.
    """
    def __init__(self, path: str):
        if not Path(path).is_absolute() or path == ":memory:":
            raise ValueError("Durable absolute ledger path required")
        self.path = path

    def reserve(self, cost_paise: int, *, now: float | None = None) -> int:
        if type(cost_paise) is not int or cost_paise < 0:
            raise ValueError("Invalid cost")
        now = time.time() if now is None else now
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute("CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, ts REAL NOT NULL, paise INTEGER NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            total, = db.execute("SELECT COALESCE(SUM(paise),0) FROM usage").fetchone()
            count, = db.execute("SELECT COUNT(*) FROM usage WHERE ts > ?", (now - 60,)).fetchone()
            # ₹360 cutoff leaves ₹40 headroom. No resets or refunds on timeout.
            if total + cost_paise > 36000 or count >= 5:
                raise ValueError("AI budget or rate limit exhausted")
            cursor = db.execute("INSERT INTO usage(ts,paise) VALUES (?,?)", (now, cost_paise))
            return cursor.lastrowid
