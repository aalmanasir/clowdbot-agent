import aiosqlite
from app.config import settings

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    status TEXT NOT NULL,
    raw_payload TEXT,
    analysis TEXT,
    action_taken TEXT,
    result TEXT
);
"""

async def init_db():
    async with aiosqlite.connect(settings.SQLITE_PATH) as db:
        await db.execute(CREATE_SQL)
        await db.commit()

async def write_event(source, event_type, actor, status, raw_payload, analysis, action_taken, result):
    async with aiosqlite.connect(settings.SQLITE_PATH) as db:
        await db.execute(
            """
            INSERT INTO event_log
            (source, event_type, actor, status, raw_payload, analysis, action_taken, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, event_type, actor, status, raw_payload, analysis, action_taken, result),
        )
        await db.commit()
