import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "parties.db"


# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Recommended for SQLite
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def init_database():

    with get_connection() as conn:

        # Main party table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL UNIQUE,

                activity_name TEXT NOT NULL,
                start_datetime TEXT NOT NULL,
                max_players INTEGER NOT NULL,

                organizer_id INTEGER NOT NULL,

                cancelled INTEGER NOT NULL DEFAULT 0,
                reminder_sent INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL
            )
        """)

        columns = conn.execute(
            "PRAGMA table_info(parties)"
        ).fetchall()

        column_names = [
            column["name"]
            for column in columns
        ]

        if "status" not in column_names:
            conn.execute("""
                ALTER TABLE parties
                ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
            """)

            conn.execute("""
                UPDATE parties
                SET status =
                    CASE
                        WHEN cancelled = 1 THEN 'cancelled'
                        ELSE 'active'
                    END
            """)

        # Party members
        conn.execute("""
            CREATE TABLE IF NOT EXISTS party_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                party_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,

                member_type TEXT NOT NULL
                    CHECK(member_type IN ('player', 'helper')),

                UNIQUE(party_id, user_id),

                FOREIGN KEY(party_id)
                    REFERENCES parties(id)
                    ON DELETE CASCADE
            )
        """)

        conn.commit()


# ============================================================
# CREATE PARTY
# ============================================================

def create_party(
    guild_id,
    channel_id,
    message_id,
    activity_name,
    start_datetime,
    max_players,
    organizer_id,
    created_at
):

    with get_connection() as conn:

        cursor = conn.execute("""
            INSERT INTO parties (
                guild_id,
                channel_id,
                message_id,
                activity_name,
                start_datetime,
                max_players,
                organizer_id,
                cancelled,
                reminder_sent,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
        """, (
            guild_id,
            channel_id,
            message_id,
            activity_name,
            start_datetime,
            max_players,
            organizer_id,
            created_at
        ))

        conn.commit()

        return cursor.lastrowid


# ============================================================
# GET ACTIVE PARTIES
# ============================================================

def get_active_parties():

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT *
            FROM parties
            WHERE status = 'active'
            ORDER BY start_datetime ASC
        """).fetchall()

        return [dict(row) for row in rows]

def complete_party(party_id):

    with get_connection() as conn:

        conn.execute("""
            UPDATE parties
            SET status = 'completed'
            WHERE id = ?
        """, (party_id,))

        conn.commit()

# ============================================================
# GET MEMBERS
# ============================================================

def get_party_members(party_id):

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT user_id, member_type
            FROM party_members
            WHERE party_id = ?
            ORDER BY id ASC
        """, (party_id,)).fetchall()

        return [dict(row) for row in rows]


# ============================================================
# ADD / CHANGE MEMBER
# ============================================================

def set_member(party_id, user_id, member_type):

    if member_type not in ("player", "helper"):
        raise ValueError("Invalid member_type")

    with get_connection() as conn:

        # If the member already exists, update their type.
        conn.execute("""
            INSERT INTO party_members (
                party_id,
                user_id,
                member_type
            )
            VALUES (?, ?, ?)

            ON CONFLICT(party_id, user_id)
            DO UPDATE SET
                member_type = excluded.member_type
        """, (
            party_id,
            user_id,
            member_type
        ))

        conn.commit()


# ============================================================
# REMOVE MEMBER
# ============================================================

def remove_member(party_id, user_id):

    with get_connection() as conn:

        conn.execute("""
            DELETE FROM party_members
            WHERE party_id = ?
              AND user_id = ?
        """, (
            party_id,
            user_id
        ))

        conn.commit()


# ============================================================
# CHANGE MAX PLAYERS
# ============================================================

def update_max_players(party_id, new_max):

    with get_connection() as conn:

        conn.execute("""
            UPDATE parties
            SET max_players = ?
            WHERE id = ?
        """, (
            new_max,
            party_id
        ))

        conn.commit()


# ============================================================
# CANCEL PARTY
# ============================================================

def cancel_party(party_id):

    with get_connection() as conn:

        conn.execute("""
            UPDATE parties
            SET status = 'cancelled'
            WHERE id = ?
        """, (party_id,))

        conn.commit()


# ============================================================
# REMINDER SENT
# ============================================================

def mark_reminder_sent(party_id):

    with get_connection() as conn:

        conn.execute("""
            UPDATE parties
            SET reminder_sent = 1
            WHERE id = ?
        """, (party_id,))

        conn.commit()


# ============================================================
# RESET REMINDER
# ============================================================

def reset_reminder(party_id):

    with get_connection() as conn:

        conn.execute("""
            UPDATE parties
            SET reminder_sent = 0
            WHERE id = ?
        """, (party_id,))

        conn.commit()