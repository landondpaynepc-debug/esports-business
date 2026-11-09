"""Local, restart-safe state. Keep data/ on persistent storage."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS panels (
                name TEXT PRIMARY KEY, message_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                claimed_by INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                original_overwrites TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_ticket_per_type
                ON tickets(owner_id, kind) WHERE status != 'closed';
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        ''')
        self.db.commit()

    def execute(self, sql, args=()):
        with self.db:
            return self.db.execute(sql, args)

    def ticket(self, channel_id):
        return self.db.execute('SELECT * FROM tickets WHERE channel_id=?', (channel_id,)).fetchone()

    def active(self, owner_id, kind):
        return self.db.execute(
            "SELECT * FROM tickets WHERE owner_id=? AND kind=? AND status!='closed'",
            (owner_id, kind),
        ).fetchone()

    def add_ticket(self, channel_id, owner_id, kind):
        self.execute(
            'INSERT INTO tickets(channel_id,owner_id,kind,created_at) VALUES(?,?,?,?)',
            (channel_id, owner_id, kind, datetime.now(timezone.utc).isoformat()),
        )

    def close(self):
        self.db.close()
