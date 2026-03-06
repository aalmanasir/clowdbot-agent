import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any

import httpx

from app.config import settings
from app.logging_config import logger
from app.db import write_event


class HealthMonitor:
    """Periodic health monitoring and self-checks."""

    def __init__(self):
        self.checks_run: int = 0
        self.last_check: float = 0
        self.last_results: Dict[str, Any] = {}

    async def run_checks(self) -> Dict[str, Any]:
        """Run all health checks and return results."""
        self.checks_run += 1
        self.last_check = time.time()

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "check_number": self.checks_run,
            "checks": {},
        }

        # Self health check
        results["checks"]["self"] = await self._check_self()

        # Database check
        results["checks"]["database"] = await self._check_database()

        # OpenAI connectivity
        results["checks"]["openai"] = await self._check_openai()

        # GitHub connectivity
        results["checks"]["github"] = await self._check_github()

        # Compute overall status
        all_ok = all(c.get("ok", False) for c in results["checks"].values())
        results["overall"] = "healthy" if all_ok else "degraded"

        self.last_results = results

        # Log any failures
        failed = [k for k, v in results["checks"].items() if not v.get("ok", False)]
        if failed:
            logger.warning("Health check degraded — failed: %s", ", ".join(failed))
            await write_event(
                source="monitoring",
                event_type="health_check",
                actor="system",
                status="degraded",
                raw_payload=str(failed),
                analysis=None,
                action_taken="alert",
                result=f"Failed checks: {', '.join(failed)}",
                severity="warning",
            )
        else:
            logger.debug("Health check passed — all systems ok")

        return results

    async def _check_self(self) -> Dict[str, Any]:
        """Check own HTTP endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://127.0.0.1:{settings.APP_PORT}/health",
                    timeout=5.0,
                )
                return {
                    "ok": resp.status_code == 200,
                    "status_code": resp.status_code,
                    "latency_ms": round(resp.elapsed.total_seconds() * 1000),
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _check_database(self) -> Dict[str, Any]:
        """Check database connectivity."""
        try:
            import aiosqlite
            async with aiosqlite.connect(settings.SQLITE_PATH) as db:
                cursor = await db.execute("SELECT COUNT(*) FROM event_log")
                count = (await cursor.fetchone())[0]
                return {"ok": True, "event_count": count}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _check_openai(self) -> Dict[str, Any]:
        """Check OpenAI API connectivity."""
        if not settings.OPENAI_API_KEY:
            return {"ok": True, "status": "not_configured", "note": "skipped"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    timeout=10.0,
                )
                return {
                    "ok": resp.status_code == 200,
                    "status_code": resp.status_code,
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _check_github(self) -> Dict[str, Any]:
        """Check GitHub API connectivity."""
        if not settings.GITHUB_TOKEN:
            return {"ok": True, "status": "not_configured", "note": "skipped"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.github.com/rate_limit",
                    headers={"Authorization": f"token {settings.GITHUB_TOKEN}"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    core = data.get("resources", {}).get("core", {})
                    return {
                        "ok": True,
                        "rate_limit_remaining": core.get("remaining"),
                        "rate_limit_total": core.get("limit"),
                    }
                return {"ok": False, "status_code": resp.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# Singleton
monitor = HealthMonitor()


async def monitoring_loop():
    """Background loop that runs health checks periodically."""
    logger.info("Monitoring loop started (interval: %ds)", settings.HEALTH_CHECK_INTERVAL)
    while True:
        try:
            await monitor.run_checks()
        except Exception as e:
            logger.error("Monitoring loop error: %s", e)
        await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL)
