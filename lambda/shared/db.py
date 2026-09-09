"""
SQLite-backed datastore for the vuln-demo app.

The DB lives at /tmp/vuln-demo.sqlite inside the Lambda execution
environment. First call seeds it with two users, four orders, and a
couple of comments. Subsequent invocations reuse it (until Lambda
cold-starts on a fresh container).
"""
import hashlib
import os
import sqlite3
from typing import Iterable

DB_PATH = "/tmp/vuln-demo.sqlite"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _seeded(c: sqlite3.Connection) -> bool:
    cur = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    return cur.fetchone() is not None


def _seed(c: sqlite3.Connection) -> None:
    c.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            note TEXT
        );

        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Two demo users. Passwords stored as plain SHA-1 — itself a small
    # finding; the headline vulns are SQLi/IDOR/etc.
    users = [
        ("alice", "alice-pass-123", "alice@example.com"),
        ("bob",   "bob-pass-456",   "bob@example.com"),
    ]
    for u, pw, email in users:
        c.execute(
            "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
            (u, hashlib.sha1(pw.encode()).hexdigest(), email),
        )

    # Alice's orders (id 1, 2). Bob's (id 3, 4).
    orders = [
        (1, "Widget A",       1999, "Alice's first widget"),
        (1, "Widget B",       4999, "Confidential: alice gift"),
        (2, "Gadget X",       2999, "Bob's gadget"),
        (2, "Premium plan", 199900, "Bob's annual subscription"),
    ]
    c.executemany(
        "INSERT INTO orders (user_id, item, amount_cents, note) VALUES (?,?,?,?)",
        orders,
    )

    c.executemany(
        "INSERT INTO comments (user_id, body) VALUES (?, ?)",
        [(1, "Welcome to the demo!"), (2, "Hello world.")],
    )

    c.commit()


def get_db() -> sqlite3.Connection:
    """Return a connection, seeding the DB on first call."""
    fresh = not os.path.exists(DB_PATH)
    c = _conn()
    if fresh or not _seeded(c):
        _seed(c)
    return c


def fetchall_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]
