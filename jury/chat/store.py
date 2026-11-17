"""Save one-on-one chats in the same SQLite file as the room checkpoints."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from jury.chat.session import ChatSession

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    persona_id TEXT NOT NULL,
    room_thread TEXT,
    room_context TEXT NOT NULL,
    brief TEXT NOT NULL,
    messages TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class ChatStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(SCHEMA)

    def save(self, s: ChatSession) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """INSERT INTO chats (id, persona_id, room_thread, room_context, brief, messages, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET messages = excluded.messages, updated_at = excluded.updated_at""",
                (s.id, s.persona_id, s.room_thread, s.room_context, json.dumps(s.brief),
                 json.dumps(s.messages), now, now),
            )

    def load(self, chat_id: str) -> ChatSession | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT id, persona_id, room_thread, room_context, brief, messages FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        return ChatSession(id=row[0], persona_id=row[1], room_thread=row[2], room_context=row[3],
                           brief=json.loads(row[4]), messages=json.loads(row[5]))

    def list(self, limit: int = 20) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                "SELECT id, persona_id, room_thread, json_array_length(messages), updated_at, "
                "json_extract(brief, '$.project_name') "
                "FROM chats ORDER BY updated_at DESC LIMIT ?", (limit,),
            ).fetchall()
        return [{"id": r[0], "persona_id": r[1], "room_thread": r[2], "messages": r[3], "updated_at": r[4],
                 "project_name": r[5] or ""} for r in rows]
