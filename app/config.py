import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Application
    APP_NAME: str = os.getenv("APP_NAME", "clowdbot-agent")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8080"))
    APP_VERSION: str = os.getenv("APP_VERSION", "0.2.0")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Discord
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    DISCORD_CHANNEL_ID: int = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

    # GitHub
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    # Operating mode: monitor | assist | execute | incident
    BOT_MODE: str = os.getenv("BOT_MODE", "assist").lower()

    # Database
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "./agent.db")

    # Shell execution
    ALLOWED_EXECUTE: bool = os.getenv("ALLOWED_EXECUTE", "false").lower() == "true"

    # Monitoring
    HEALTH_CHECK_INTERVAL: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
    UPTIME_START: float = 0.0  # Set at runtime

    @classmethod
    def masked_summary(cls) -> dict:
        """Return config summary with secrets masked."""
        def _mask(val: str) -> str:
            if not val or len(val) < 8:
                return "***" if val else "(not set)"
            return val[:4] + "..." + val[-4:]

        return {
            "app_name": cls.APP_NAME,
            "app_env": cls.APP_ENV,
            "app_version": cls.APP_VERSION,
            "host": f"{cls.APP_HOST}:{cls.APP_PORT}",
            "log_level": cls.LOG_LEVEL,
            "bot_mode": cls.BOT_MODE,
            "openai_key": _mask(cls.OPENAI_API_KEY),
            "openai_model": cls.OPENAI_MODEL,
            "discord_token": _mask(cls.DISCORD_BOT_TOKEN),
            "discord_channel": cls.DISCORD_CHANNEL_ID,
            "github_token": _mask(cls.GITHUB_TOKEN),
            "github_webhook_secret": "set" if cls.GITHUB_WEBHOOK_SECRET else "(not set)",
            "sqlite_path": cls.SQLITE_PATH,
            "allowed_execute": cls.ALLOWED_EXECUTE,
        }


settings = Settings()
