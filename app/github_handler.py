import hmac
import hashlib
import json
from typing import Optional

from github import Github

from app.config import settings
from app.logging_config import logger
from app.openai_client import analyze_event
from app.db import write_event

gh = Github(settings.GITHUB_TOKEN) if settings.GITHUB_TOKEN else None


def verify_github_signature(body: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True  # No secret configured, skip verification
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_event_summary(event_type: str, payload: dict) -> dict:
    """Extract a human-readable summary from a GitHub event payload."""
    actor = payload.get("sender", {}).get("login", "unknown")
    repo = payload.get("repository", {}).get("full_name", "unknown")
    action = payload.get("action", "")

    summary = {
        "event_type": event_type,
        "actor": actor,
        "repo": repo,
        "action": action,
    }

    if event_type == "push":
        commits = payload.get("commits", [])
        summary["branch"] = payload.get("ref", "").replace("refs/heads/", "")
        summary["commit_count"] = len(commits)
        summary["commits"] = [
            {"sha": c.get("id", "")[:8], "message": c.get("message", "").split("\n")[0]}
            for c in commits[:5]
        ]

    elif event_type == "pull_request":
        pr = payload.get("pull_request", {})
        summary["pr_number"] = pr.get("number")
        summary["pr_title"] = pr.get("title", "")
        summary["pr_state"] = pr.get("state", "")
        summary["pr_merged"] = pr.get("merged", False)
        summary["base"] = pr.get("base", {}).get("ref", "")
        summary["head"] = pr.get("head", {}).get("ref", "")

    elif event_type == "issues":
        issue = payload.get("issue", {})
        summary["issue_number"] = issue.get("number")
        summary["issue_title"] = issue.get("title", "")
        summary["issue_state"] = issue.get("state", "")
        summary["labels"] = [l.get("name", "") for l in issue.get("labels", [])]

    elif event_type == "release":
        release = payload.get("release", {})
        summary["tag"] = release.get("tag_name", "")
        summary["release_name"] = release.get("name", "")
        summary["prerelease"] = release.get("prerelease", False)
        summary["draft"] = release.get("draft", False)

    elif event_type in ("check_run", "check_suite"):
        check = payload.get("check_run", payload.get("check_suite", {}))
        summary["check_name"] = check.get("name", check.get("app", {}).get("name", ""))
        summary["conclusion"] = check.get("conclusion", "")
        summary["status"] = check.get("status", "")

    elif event_type == "workflow_run":
        wf = payload.get("workflow_run", {})
        summary["workflow_name"] = wf.get("name", "")
        summary["conclusion"] = wf.get("conclusion", "")
        summary["status"] = wf.get("status", "")
        summary["branch"] = wf.get("head_branch", "")

    elif event_type == "create" or event_type == "delete":
        summary["ref_type"] = payload.get("ref_type", "")
        summary["ref"] = payload.get("ref", "")

    elif event_type == "issue_comment":
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        summary["issue_number"] = issue.get("number")
        summary["issue_title"] = issue.get("title", "")
        summary["comment_body"] = (comment.get("body", "") or "")[:500]

    elif event_type == "star":
        summary["starred"] = action == "created"

    return summary


def _classify_severity(event_type: str, payload: dict) -> str:
    """Determine event severity."""
    action = payload.get("action", "")

    # CI failures are warnings
    if event_type in ("check_run", "check_suite", "workflow_run"):
        conclusion = (
            payload.get("check_run", {}).get("conclusion")
            or payload.get("check_suite", {}).get("conclusion")
            or payload.get("workflow_run", {}).get("conclusion")
            or ""
        )
        if conclusion in ("failure", "timed_out", "action_required"):
            return "warning"

    # Force pushes and deletions are warnings
    if event_type == "push" and payload.get("forced", False):
        return "warning"
    if event_type == "delete":
        return "warning"

    # Closed issues/PRs with security labels
    if event_type == "issues":
        labels = [l.get("name", "").lower() for l in payload.get("issue", {}).get("labels", [])]
        if any(l in ("security", "critical", "urgent", "bug") for l in labels):
            return "warning"

    return "info"


async def process_github_event(event_type: str, payload: dict) -> dict:
    """Process an incoming GitHub webhook event."""
    summary = _extract_event_summary(event_type, payload)
    actor = summary["actor"]
    severity = _classify_severity(event_type, payload)

    logger.info(
        "GitHub event: type=%s actor=%s repo=%s severity=%s",
        event_type, actor, summary.get("repo"), severity,
    )

    # Truncate raw payload for storage
    raw_truncated = json.dumps(payload)[:12000]

    # Analyze with OpenAI if available
    analysis_input = json.dumps(summary, indent=2)
    analysis = await analyze_event(
        f"GitHub event type: {event_type}\nSummary:\n{analysis_input}"
    )

    event_id = await write_event(
        source="github",
        event_type=event_type,
        actor=actor,
        status="processed",
        raw_payload=raw_truncated,
        analysis=analysis,
        action_taken="analysis_only",
        result="ok",
        severity=severity,
    )

    return {
        "ok": True,
        "event_id": event_id,
        "event_type": event_type,
        "severity": severity,
        "summary": summary,
        "analysis": analysis,
    }
