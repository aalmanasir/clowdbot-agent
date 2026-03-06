import hmac
import hashlib
import json
from github import Github
from app.config import settings
from app.openai_client import analyze_event
from app.db import write_event

gh = Github(settings.GITHUB_TOKEN) if settings.GITHUB_TOKEN else None

def verify_github_signature(body: bytes, signature: str) -> bool:
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def process_github_event(event_type: str, payload: dict):
    actor = payload.get("sender", {}).get("login", "unknown")
    summary_source = json.dumps(payload)[:12000]
    analysis = await analyze_event(f"GitHub event type: {event_type}\nPayload:\n{summary_source}")

    await write_event(
        source="github",
        event_type=event_type,
        actor=actor,
        status="processed",
        raw_payload=summary_source,
        analysis=analysis,
        action_taken="analysis_only",
        result="ok"
    )
    return {"ok": True, "analysis": analysis}
