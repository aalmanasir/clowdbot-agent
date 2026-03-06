import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from app.config import settings
from app.db import init_db
from app.github_handler import verify_github_signature, process_github_event
from app.discord_bot import start_discord

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.DISCORD_BOT_TOKEN:
        threading.Thread(target=start_discord, daemon=True).start()
    yield

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "mode": settings.BOT_MODE}

@app.post("/webhook/github")
async def github_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(body, sig):
        return Response(status_code=403, content="Invalid signature")
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    payload = await request.json()
    result = await process_github_event(event_type, payload)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
