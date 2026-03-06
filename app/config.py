import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME = os.getenv("APP_NAME", "clowdbot-agent")
    APP_ENV = os.getenv("APP_ENV", "development")
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8080"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    BOT_MODE = os.getenv("BOT_MODE", "assist").lower()
    SQLITE_PATH = os.getenv("SQLITE_PATH", "./agent.db")
    ALLOWED_EXECUTE = os.getenv("ALLOWED_EXECUTE", "false").lower() == "true"

settings = Settings()
