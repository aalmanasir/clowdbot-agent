import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.config import settings
from app.db import get_event_stats, get_events, init_db
from app.monitoring import monitor
from app.shell_utils import run_command


PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "clowdbot-agent-mcp"
SERVER_VERSION = settings.APP_VERSION


def _content(data: Any) -> list[dict[str, str]]:
    return [{"type": "text", "text": json.dumps(data, indent=2, sort_keys=True)}]


def _bool_env(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _file_status(path: str) -> str:
    if not path:
        return "not_set"
    return "present" if Path(path).exists() else "missing"


async def tool_status(_: dict[str, Any]) -> dict[str, Any]:
    stats = await get_event_stats()
    uptime_seconds = max(0, int(time.time() - settings.UPTIME_START)) if settings.UPTIME_START else 0
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "mode": settings.BOT_MODE,
        "uptime_seconds": uptime_seconds,
        "events": stats,
        "integrations": {
            "openai": "configured" if _bool_env("OPENAI_API_KEY") else "not_set",
            "github": "configured" if _bool_env("GITHUB_TOKEN") else "not_set",
            "telegram": "configured" if _bool_env("TELEGRAM_BOT_TOKEN") else "not_set",
            "google_cloud": settings.GOOGLE_CLOUD_PROJECT or "not_set",
        },
    }


async def tool_health(_: dict[str, Any]) -> dict[str, Any]:
    return await monitor.run_checks()


async def tool_readiness(_: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "openai_api_key": bool(settings.OPENAI_API_KEY),
        "google_cloud_project": bool(settings.GOOGLE_CLOUD_PROJECT),
        "google_maps_api_key": bool(settings.GOOGLE_MAPS_API_KEY),
        "github_repository": bool(settings.GITHUB_REPOSITORY),
        "telegram_bot": bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
    }
    missing = [name for name, ok in checks.items() if not ok]
    return {"ready": not missing, "mode": settings.BOT_MODE, "checks": checks, "missing": missing}


async def tool_recent_events(arguments: dict[str, Any]) -> dict[str, Any]:
    limit = int(arguments.get("limit", 10))
    limit = max(1, min(limit, 50))
    rows = await get_events(
        limit=limit,
        source=arguments.get("source") or None,
        event_type=arguments.get("event_type") or None,
        status=arguments.get("status") or None,
        severity=arguments.get("severity") or None,
    )
    return {"count": len(rows), "events": rows}


async def tool_google_cloud_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": settings.GOOGLE_CLOUD_PROJECT or "not_set",
        "credentials": _file_status(settings.GOOGLE_APPLICATION_CREDENTIALS),
        "credentials_path": settings.GOOGLE_APPLICATION_CREDENTIALS or "not_set",
        "maps_api_key": "configured" if _bool_env("GOOGLE_MAPS_API_KEY") else "not_set",
    }


async def tool_openai_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "configured": bool(settings.OPENAI_API_KEY),
        "model": settings.OPENAI_MODEL,
        "api": "chat_completions",
        "note": "OpenAI key is masked and never returned by MCP.",
    }


async def tool_github_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": settings.GITHUB_REPOSITORY or "not_set",
        "token": "configured" if _bool_env("GITHUB_TOKEN") else "not_set",
        "webhook_secret": "configured" if _bool_env("GITHUB_WEBHOOK_SECRET") else "not_set",
    }


async def tool_telegram_status(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "bot_token": "configured" if _bool_env("TELEGRAM_BOT_TOKEN") else "not_set",
        "allowed_chat_id": "configured" if settings.TELEGRAM_CHAT_ID else "not_set",
        "poll_interval_seconds": settings.TELEGRAM_POLL_INTERVAL,
    }


async def tool_run_safe_command(arguments: dict[str, Any]) -> dict[str, Any]:
    command = str(arguments.get("command", "")).strip()
    if not command:
        return {"ok": False, "error": "command is required"}
    return run_command(command)


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

TOOLS: dict[str, tuple[dict[str, Any], ToolHandler]] = {
    "clowdbot_status": (
        {
            "name": "clowdbot_status",
            "description": "Use this when you need app mode, integration readiness, uptime, and event summary.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_status,
    ),
    "clowdbot_health": (
        {
            "name": "clowdbot_health",
            "description": "Use this when you need a live health check for self, database, OpenAI, and GitHub.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_health,
    ),
    "clowdbot_readiness": (
        {
            "name": "clowdbot_readiness",
            "description": "Use this when you need deployment readiness and missing non-secret setup items.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_readiness,
    ),
    "clowdbot_recent_events": (
        {
            "name": "clowdbot_recent_events",
            "description": "Use this when you need recent event log entries with optional filters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    "source": {"type": "string"},
                    "event_type": {"type": "string"},
                    "status": {"type": "string"},
                    "severity": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_recent_events,
    ),
    "google_cloud_status": (
        {
            "name": "google_cloud_status",
            "description": "Use this when you need Google Cloud project and service-account file readiness.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_google_cloud_status,
    ),
    "openai_status": (
        {
            "name": "openai_status",
            "description": "Use this when you need OpenAI API readiness and model settings without exposing secrets.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_openai_status,
    ),
    "github_status": (
        {
            "name": "github_status",
            "description": "Use this when you need GitHub repository, token, and webhook configuration status.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_github_status,
    ),
    "telegram_status": (
        {
            "name": "telegram_status",
            "description": "Use this when you need Telegram bot and allowed chat configuration status without exposing secrets.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        },
        tool_telegram_status,
    ),
    "run_safe_command": (
        {
            "name": "run_safe_command",
            "description": "Use this only for existing allowlisted local commands; execution is disabled unless ALLOWED_EXECUTE=true.",
            "inputSchema": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Allowlisted command to run."}},
                "required": ["command"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
        },
        tool_run_safe_command,
    ),
}


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")

    if request_id is None:
        return None

    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "tools/list":
        return _response(request_id, {"tools": [definition for definition, _ in TOOLS.values()]})

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            return _error(request_id, -32602, f"Unknown tool: {name}")
        try:
            _, handler = TOOLS[name]
            result = await handler(arguments)
            return _response(request_id, {"content": _content(result), "isError": False})
        except Exception as exc:
            return _response(request_id, {"content": _content({"ok": False, "error": str(exc)}), "isError": True})

    return _error(request_id, -32601, f"Method not found: {method}")


async def serve() -> None:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(sys.stderr)
    await init_db()
    settings.UPTIME_START = time.time()
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            message = json.loads(line)
            response = await handle_request(message)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"Parse error: {exc}")
        except Exception as exc:
            response = _error(None, -32603, f"Internal error: {exc}")
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
