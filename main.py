import asyncio
import time
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import logger
from app.db import init_db
from app.discord_bot import start_discord
from app.routes import router
from app.monitoring import monitor, monitoring_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    settings.UPTIME_START = time.time()
    logger.info(
        "Starting %s v%s [%s mode] on %s:%d",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.BOT_MODE.upper(),
        settings.APP_HOST,
        settings.APP_PORT,
    )

    # Initialize database
    await init_db()

    # Start Discord bot in background thread
    if settings.DISCORD_BOT_TOKEN:
        discord_thread = threading.Thread(target=start_discord, daemon=True, name="discord-bot")
        discord_thread.start()
        logger.info("Discord bot thread started")
    else:
        logger.info("Discord bot skipped (no token)")

    # Start monitoring loop
    monitor_task = asyncio.create_task(monitoring_loop())
    logger.info("Monitoring loop started")

    # Log integration status
    logger.info(
        "Integrations — OpenAI: %s | GitHub: %s | Discord: %s",
        "ready" if settings.OPENAI_API_KEY else "not configured",
        "ready" if settings.GITHUB_TOKEN else "not configured",
        "ready" if settings.DISCORD_BOT_TOKEN else "not configured",
    )

    yield

    # Shutdown
    monitor_task.cancel()
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Autonomous operations & engineering copilot",
    lifespan=lifespan,
)

# CORS — allow all in development, restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routes
app.include_router(router)


# Monitoring endpoint (separate from router for direct access)
@app.get("/monitoring/health")
async def monitoring_health():
    """Run health checks on demand and return results."""
    results = await monitor.run_checks()
    return results


@app.get("/monitoring/last")
async def monitoring_last():
    """Return results of the last periodic health check."""
    return monitor.last_results or {"message": "No checks run yet"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_ENV == "development",
        log_level=settings.LOG_LEVEL.lower(),
    )
