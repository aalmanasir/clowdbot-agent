import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import aiosqlite

from app.config import settings
from app.logging_config import logger

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    status TEXT NOT NULL,
    raw_payload TEXT,
    analysis TEXT,
    action_taken TEXT,
    result TEXT
);

CREATE INDEX IF NOT EXISTS idx_event_source ON event_log(source);
CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_created ON event_log(created_at);
CREATE INDEX IF NOT EXISTS idx_event_status ON event_log(status);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection with row factory enabled."""
    db = await aiosqlite.connect(settings.SQLITE_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Initialize database schema."""
    try:
        async with aiosqlite.connect(settings.SQLITE_PATH) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()
        logger.info("Database initialized at %s", settings.SQLITE_PATH)
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise


async def write_event(
    source: str,
    event_type: str,
    actor: Optional[str],
    status: str,
    raw_payload: Optional[str] = None,
    analysis: Optional[str] = None,
    action_taken: Optional[str] = None,
    result: Optional[str] = None,
    severity: str = "info",
) -> int:
    """Write an event to the log and return the new row ID."""
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                """
                INSERT INTO event_log
                (source, event_type, actor, severity, status, raw_payload, analysis, action_taken, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source, event_type, actor, severity, status, raw_payload, analysis, action_taken, result),
            )
            await db.commit()
            row_id = cursor.lastrowid
            logger.debug("Event logged: id=%d source=%s type=%s", row_id, source, event_type)
            return row_id
        finally:
            await db.close()
    except Exception as e:
        logger.error("Failed to write event: %s", e)
        raise


async def get_events(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query events with optional filters."""
    conditions = []
    params = []

    if source:
        conditions.append("source = ?")
        params.append(source)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if since:
        conditions.append("created_at >= ?")
        params.append(since)

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    query = f"""
        SELECT id, created_at, source, event_type, actor, severity, status,
               analysis, action_taken, result
        FROM event_log
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    db = await get_db()
    try:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_event_by_id(event_id: int) -> Optional[Dict[str, Any]]:
    """Get a single event by ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM event_log WHERE id = ?", (event_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_event_stats() -> Dict[str, Any]:
    """Get aggregate event statistics."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) as total FROM event_log")
        total = (await cursor.fetchone())["total"]

        cursor = await db.execute(
            "SELECT source, COUNT(*) as count FROM event_log GROUP BY source ORDER BY count DESC"
        )
        by_source = {row["source"]: row["count"] for row in await cursor.fetchall()}

        cursor = await db.execute(
            "SELECT status, COUNT(*) as count FROM event_log GROUP BY status ORDER BY count DESC"
        )
        by_status = {row["status"]: row["count"] for row in await cursor.fetchall()}

        cursor = await db.execute(
            "SELECT severity, COUNT(*) as count FROM event_log GROUP BY severity ORDER BY count DESC"
        )
        by_severity = {row["severity"]: row["count"] for row in await cursor.fetchall()}

        cursor = await db.execute(
            "SELECT MAX(created_at) as latest FROM event_log"
        )
        latest = (await cursor.fetchone())["latest"]

        return {
            "total_events": total,
            "by_source": by_source,
            "by_status": by_status,
            "by_severity": by_severity,
            "latest_event": latest,
        }
    finally:
        await db.close()
