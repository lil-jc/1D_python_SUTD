"""SQLite storage and business rules for one-visitor return passes."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from time import time

from park import RIDES, window_label

WINDOW_SECONDS = 5 * 60
MINIMUM_WINDOW_LEFT = 2 * 60
HORIZON_SECONDS = 90 * 60


@contextmanager
def connection():
    """Commit successful operations and roll back failed ones before closing."""
    default_path = Path(__file__).with_name("skytrail.sqlite3")
    db = sqlite3.connect(os.environ.get("SKYTRAIL_DB") or default_path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS visitors (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS passes (
                code TEXT PRIMARY KEY,
                visitor_id INTEGER NOT NULL REFERENCES visitors(id),
                ride TEXT NOT NULL,
                start_at INTEGER NOT NULL,
                end_at INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'booked'
                    CHECK (state IN ('booked', 'cancelled', 'checked_in'))
            );
            CREATE INDEX IF NOT EXISTS ride_window ON passes (ride, start_at);
            CREATE INDEX IF NOT EXISTS visitor_window ON passes (visitor_id, end_at);
        """)


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)


def register(username, password):
    """Create a visitor and return their ID."""
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,24}", username):
        raise ValueError("Use 3–24 letters, digits or underscores for your username.")
    if not 8 <= len(password) <= 128:
        raise ValueError("Use a password of 8–128 characters.")
    salt = secrets.token_bytes(16)
    try:
        with connection() as db:
            result = db.execute(
                "INSERT INTO visitors (username, salt, password_hash) VALUES (?, ?, ?)",
                (username, salt, password_hash(password, salt)),
            )
            return result.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("That username is already taken.") from None


def authenticate(username, password):
    """Return the account ID for valid credentials."""
    if len(password) > 128:
        return None
    with connection() as db:
        visitor = db.execute(
            "SELECT * FROM visitors WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
    if visitor and hmac.compare_digest(
        visitor["password_hash"], password_hash(password, visitor["salt"])
    ):
        return visitor["id"]
    return None


def available_window(db, visitor_id, ride, now):
    """Find the first bookable window and return it with its remaining capacity."""
    if ride not in RIDES:
        raise ValueError("Choose an attraction from the park.")
    existing = db.execute(
        """SELECT 1 FROM passes
           WHERE visitor_id = ? AND ride = ? AND state = 'booked' AND end_at > ?""",
        (visitor_id, ride, now),
    ).fetchone()
    if existing:
        raise ValueError("You already have an active pass for this ride.")

    first = (now // WINDOW_SECONDS) * WINDOW_SECONDS
    if first + WINDOW_SECONDS - now < MINIMUM_WINDOW_LEFT:
        first += WINDOW_SECONDS
    latest = now + HORIZON_SECONDS

    # All rides share the same window boundaries, so overlap means equal start times.
    conflicts = {
        row["start_at"]
        for row in db.execute(
            """SELECT start_at FROM passes WHERE visitor_id = ?
               AND start_at BETWEEN ? AND ? AND state != 'cancelled'""",
            (visitor_id, first, latest),
        )
    }
    occupied = {
        row["start_at"]: row["taken"]
        for row in db.execute(
            """SELECT start_at, COUNT(*) AS taken FROM passes WHERE ride = ?
               AND start_at BETWEEN ? AND ? AND state != 'cancelled'
               GROUP BY start_at""",
            (ride, first, latest),
        )
    }

    for start in range(first, latest + 1, WINDOW_SECONDS):
        remaining = RIDES[ride]["capacity"] - occupied.get(start, 0)
        if remaining > 0 and start not in conflicts:
            return start, start + WINDOW_SECONDS, remaining
    raise ValueError("No return window is currently available in the next 90 minutes.")


def join_queue(visitor_id, ride, offered_start, now=None):
    """Recheck the offered window under a write lock before inserting the pass."""
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time()) if now is None else now
        start, end, _ = available_window(db, visitor_id, ride, now)
        if start != offered_start:
            raise ValueError("Availability changed. Review the new return window before joining.")
        code = secrets.token_hex(8).upper()
        db.execute(
            "INSERT INTO passes (code, visitor_id, ride, start_at, end_at) VALUES (?, ?, ?, ?, ?)",
            (code, visitor_id, ride, start, end),
        )
    return start, end


def visitor_passes(visitor_id):
    with connection() as db:
        return db.execute(
            "SELECT * FROM passes WHERE visitor_id = ? ORDER BY start_at, ride",
            (visitor_id,),
        ).fetchall()


def pass_status(ticket, now):
    if ticket["state"] == "checked_in":
        return "Checked in"
    if ticket["state"] == "cancelled":
        return "Cancelled"
    if now >= ticket["end_at"]:
        return "Missed window"
    if now < ticket["start_at"]:
        return "Upcoming"
    return "Ready now"


def cancel_pass(visitor_id, code, now=None):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time()) if now is None else now
        result = db.execute(
            """UPDATE passes SET state = 'cancelled'
               WHERE code = ? AND visitor_id = ? AND state = 'booked' AND end_at > ?""",
            (code, visitor_id, now),
        )
        if result.rowcount != 1:
            raise ValueError("This pass can no longer be cancelled.")


def check_in(ride, code, now=None):
    """Admit the holder once, at the right attraction and during their window."""
    code = code.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{16}", code):
        raise ValueError("Scan or enter a 16-character Skytrail pass code.")

    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        now = int(time()) if now is None else now
        ticket = db.execute("SELECT * FROM passes WHERE code = ?", (code,)).fetchone()
        if not ticket:
            raise ValueError("No pass matches this code.")
        if ticket["ride"] != ride:
            raise ValueError("This pass is for a different attraction.")
        status = pass_status(ticket, now)
        if status == "Upcoming":
            window = window_label(ticket["start_at"], ticket["end_at"])
            raise ValueError(f"This pass is too early. Return window: {window}.")
        if status != "Ready now":
            raise ValueError(f"Admission denied. Pass status: {status}.")
        db.execute("UPDATE passes SET state = 'checked_in' WHERE code = ?", (code,))
