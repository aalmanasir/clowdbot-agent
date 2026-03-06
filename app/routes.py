import json
import time
from typing import Optional

from fastapi import APIRouter, Query, Request, Response, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.logging_config import logger
from app.db import get_events, get_event_by_id, get_event_stats, write_event
from app.github_handler import verify_github_signature, process_github_event
from app.openai_client import analyze_event

router = APIRouter()


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok", "mode": settings.BOT_MODE}


@router.get("/status")
async def status():
    """Detailed system status."""
    uptime_seconds = time.time() - settings.UPTIME_START
    stats = await get_event_stats()

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "mode": settings.BOT_MODE,
        "uptime_seconds": round(uptime_seconds, 1),
        "integrations": {
            "openai": "configured" if settings.OPENAI_API_KEY else "not_set",
            "discord": "configured" if settings.DISCORD_BOT_TOKEN else "not_set",
            "github": "configured" if settings.GITHUB_TOKEN else "not_set",
            "github_webhook": "configured" if settings.GITHUB_WEBHOOK_SECRET else "not_set",
        },
        "events": stats,
    }


@router.get("/config")
async def config():
    """Show configuration with secrets masked."""
    return settings.masked_summary()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@router.get("/events")
async def list_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    source: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None, description="ISO timestamp filter"),
):
    """List events with optional filters."""
    events = await get_events(
        limit=limit,
        offset=offset,
        source=source,
        event_type=event_type,
        status=status,
        severity=severity,
        since=since,
    )
    return {"count": len(events), "offset": offset, "events": events}


@router.get("/events/{event_id}")
async def get_event(event_id: int):
    """Get a single event by ID."""
    event = await get_event_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/events/stats/summary")
async def event_stats():
    """Get aggregate event statistics."""
    return await get_event_stats()


# ---------------------------------------------------------------------------
# GitHub Webhook
# ---------------------------------------------------------------------------

@router.post("/webhook/github")
async def github_webhook(request: Request):
    """Receive and process GitHub webhook events."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not verify_github_signature(body, sig):
        logger.warning("GitHub webhook: invalid signature")
        return Response(status_code=403, content="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "unknown")

    try:
        payload = await request.json()
    except Exception:
        logger.error("GitHub webhook: invalid JSON body")
        return Response(status_code=400, content="Invalid JSON")

    try:
        result = await process_github_event(event_type, payload)
        return result
    except Exception as e:
        logger.error("GitHub webhook processing failed: %s", e)
        await write_event(
            source="github",
            event_type=event_type,
            actor=payload.get("sender", {}).get("login", "unknown"),
            status="error",
            raw_payload=json.dumps(payload)[:5000],
            analysis=None,
            action_taken="processing_failed",
            result=str(e),
            severity="error",
        )
        raise HTTPException(status_code=500, detail="Event processing failed")


# ---------------------------------------------------------------------------
# Manual Triggers
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    text: str
    source: str = "api"


@router.post("/analyze")
async def manual_analyze(req: AnalyzeRequest):
    """Manually trigger AI analysis."""
    analysis = await analyze_event(req.text)

    event_id = await write_event(
        source=req.source,
        event_type="manual_analyze",
        actor="api",
        status="processed",
        raw_payload=req.text[:5000],
        analysis=analysis,
        action_taken="analysis_only",
        result="ok",
    )

    return {
        "ok": True,
        "event_id": event_id,
        "analysis": analysis,
    }


class ManualEventRequest(BaseModel):
    source: str
    event_type: str
    actor: str = "api"
    severity: str = "info"
    description: str = ""


@router.post("/events/manual")
async def create_manual_event(req: ManualEventRequest):
    """Manually create an event in the log."""
    event_id = await write_event(
        source=req.source,
        event_type=req.event_type,
        actor=req.actor,
        status="manual",
        raw_payload=req.description[:5000],
        analysis=None,
        action_taken="manual_entry",
        result="ok",
        severity=req.severity,
    )

    return {"ok": True, "event_id": event_id}
