"""Reviews and their event log, in the same SQLite file as the graph checkpoints.

Every event a review emits is stored with a sequence number, so the browser can
reconnect (or reload) and replay from where it left off.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY,
        project_name TEXT NOT NULL,
        repo_url TEXT NOT NULL,
        persona_ids TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS review_events (
        review_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        event TEXT NOT NULL,
        PRIMARY KEY (review_id, seq)
    )""",
]
TERMINAL = {"done", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with self._db() as db, db:
            db.execute("PRAGMA journal_mode=WAL")  # the SSE reader must not block the review writer
            for stmt in SCHEMA:
                db.execute(stmt)

    def _db(self):
        return closing(sqlite3.connect(self.path, timeout=10))

    def create(self, review_id: str, project_name: str, repo_url: str, persona_ids: list[str]) -> None:
        with self._db() as db, db:
            db.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, ?)",
                       (review_id, project_name, repo_url, json.dumps(persona_ids), _now()))

    def rename(self, review_id: str, project_name: str, repo_url: str) -> None:
        with self._db() as db, db:
            db.execute("UPDATE reviews SET project_name = ?, repo_url = ? WHERE id = ?",
                       (project_name, repo_url, review_id))

    def get(self, review_id: str) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT id, project_name, repo_url, persona_ids, created_at FROM reviews WHERE id = ?",
                           (review_id,)).fetchone()
        return None if r is None else {"id": r[0], "project_name": r[1], "repo_url": r[2],
                                       "persona_ids": json.loads(r[3]), "created_at": r[4]}

    def recent(self, limit: int = 30) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT id FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{**self.get(r[0]), "status": self.status(r[0])} for r in rows]

    def add_event(self, review_id: str, event: dict) -> int:
        with self._db() as db, db:
            (last,) = db.execute("SELECT COALESCE(MAX(seq), 0) FROM review_events WHERE review_id = ?",
                                 (review_id,)).fetchone()
            db.execute("INSERT INTO review_events VALUES (?, ?, ?)", (review_id, last + 1, json.dumps(event)))
        return last + 1

    def events_after(self, review_id: str, after: int = 0) -> list[tuple[int, dict]]:
        with self._db() as db:
            rows = db.execute("SELECT seq, event FROM review_events WHERE review_id = ? AND seq > ? ORDER BY seq",
                              (review_id, after)).fetchall()
        return [(seq, json.loads(e)) for seq, e in rows]

    def status(self, review_id: str) -> str:
        """running | paused | done | error, from the last lifecycle event."""
        with self._db() as db:
            rows = db.execute("SELECT event FROM review_events WHERE review_id = ? ORDER BY seq DESC LIMIT 20",
                              (review_id,)).fetchall()
        for (e,) in rows:
            t = json.loads(e)["type"]
            if t in TERMINAL or t == "paused":
                return t
            if t == "resumed":
                return "running"
        return "running"
